"""Persistent scene editor for the Qt preview; does not run the OBS engine."""
import json
import subprocess
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

VALID_SOURCE_TYPES = (
    "Text", "Image", "Color",
    "Screen", "Display Capture", "Screen (Display Capture)",
    "Particular Screen", "Window Capture", "Particular Screen (Window Capture)",
    "Video", "Media Source", "Video (Media Source)",
)


class Workspace(QtCore.QObject):
    def __init__(self, window, canvas_label, path):
        super().__init__(window)
        self.window, self.canvas, self.path = window, canvas_label, Path(path)
        self.scenes = window.findChild(QtWidgets.QListWidget, "scenes")
        self.sources = window.findChild(QtWidgets.QListView, "sources")
        self.model = QtGui.QStandardItemModel(self)
        self.sources.setModel(self.model)
        self.scenes.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.NoDragDrop)
        self.sources.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.NoDragDrop)
        self.scenes.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sources.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data = [{"name": "Scene 1", "sources": []}]
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                assert isinstance(data, list) and data
                for scene in data:
                    assert isinstance(scene["name"], str) and isinstance(scene["sources"], list)
                    for source in scene["sources"]:
                        assert any(source["type"].startswith(t) or t.startswith(source["type"]) for t in VALID_SOURCE_TYPES)
                        assert isinstance(source["name"], str) and isinstance(source["value"], str)
                self.data = data
            except (ValueError, KeyError, TypeError, AssertionError):
                # Preserve the invalid file for recovery before saving a new workspace.
                backup = self.path.with_suffix(".invalid.json")
                backup.write_bytes(self.path.read_bytes())
                QtWidgets.QMessageBox.warning(window, "Workspace recovery", f"Saved unreadable workspace to {backup}")
        self.scenes.clear()
        self.scenes.addItems([s["name"] for s in self.data])
        self.scenes.currentRowChanged.connect(self.show_scene)
        self.model.itemChanged.connect(self.visibility_changed)
        self.scenes.itemDoubleClicked.connect(lambda *_: self.rename_scene())
        self.sources.doubleClicked.connect(lambda *_: self.edit_source())
        # In the preview, don't leave unimplemented OBS actions silently clickable.
        for action in window.findChildren(QtGui.QAction):
            if action.menu() is None:
                action.setEnabled(False)
        bindings = {
            "actionAddScene": self.add_scene, "actionRemoveScene": self.remove_scene,
            "actionAddSource": self.add_source, "actionRemoveSource": self.remove_source,
            "actionSceneUp": lambda: self.move_scene(-1), "actionSceneDown": lambda: self.move_scene(1),
            "actionSourceUp": lambda: self.move_source(-1), "actionSourceDown": lambda: self.move_source(1),
            "actionSourceProperties": self.edit_source, "actionE_xit": window.close,
        }
        for name, callback in bindings.items():
            action = window.findChild(QtGui.QAction, name)
            if action:
                action.setEnabled(True)
                action.triggered.connect(callback)
        for name in ("sourceFiltersButton", "sourceInteractButton"):
            btn = window.findChild(QtWidgets.QWidget, name)
            if btn:
                btn.setEnabled(False)
        props_btn = window.findChild(QtWidgets.QPushButton, "sourcePropertiesButton")
        if props_btn:
            props_btn.clicked.connect(self.edit_source)
        for view, callback in ((self.scenes, self.scene_menu), (self.sources, self.source_menu)):
            view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(callback)
        self.canvas.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.canvas.installEventFilter(self)
        self.scenes.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if obj is self.canvas and event.type() == QtCore.QEvent.Type.Resize:
            self.render()
        return False

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:
            QtWidgets.QMessageBox.warning(self.window, "Could not save workspace", str(error))

    def scene(self):
        row = self.scenes.currentRow()
        return self.data[row] if 0 <= row < len(self.data) else None

    def show_scene(self, *_):
        self.model.blockSignals(True)
        self.model.clear()
        scene = self.scene()
        if scene:
            for source in scene["sources"]:
                item = QtGui.QStandardItem(source["name"])
                item.setToolTip(source["type"] + " source — double-click to edit")
                item.setCheckable(True)
                item.setCheckState(QtCore.Qt.CheckState.Checked if source.get("visible", True) else QtCore.Qt.CheckState.Unchecked)
                item.setEditable(False)
                self.model.appendRow(item)
        self.model.blockSignals(False)
        if self.model.rowCount():
            self.sources.setCurrentIndex(self.model.index(0, 0))
        self.render()

    def name(self, title, initial, existing):
        value, ok = QtWidgets.QInputDialog.getText(self.window, title, "Name:", text=initial)
        if not ok:
            return None
        value = value.strip()
        if not value or value.casefold() in [n.casefold() for n in existing]:
            QtWidgets.QMessageBox.warning(self.window, title, "Enter a non-empty, unique name.")
            return None
        return value

    def add_scene(self):
        name = self.name("Create scene", "New scene", [s["name"] for s in self.data])
        if name:
            self.data.append({"name": name, "sources": []})
            self.scenes.addItem(name)
            self.scenes.setCurrentRow(len(self.data) - 1)
            self.save()

    def rename_scene(self):
        row = self.scenes.currentRow()
        scene = self.scene()
        if not scene:
            return
        name = self.name("Rename scene", scene["name"], [s["name"] for i, s in enumerate(self.data) if i != row])
        if name:
            scene["name"] = name
            self.scenes.item(row).setText(name)
            self.save()
            self.render()

    def confirm(self, name):
        return QtWidgets.QMessageBox.question(self.window, "Remove", f'Remove "{name}"?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No) == QtWidgets.QMessageBox.StandardButton.Yes

    def remove_scene(self):
        if len(self.data) == 1:
            QtWidgets.QMessageBox.information(self.window, "Keep one scene", "Create another scene before deleting the last scene.")
            return
        row = self.scenes.currentRow()
        if self.scene() and self.confirm(self.scene()["name"]):
            self.scenes.blockSignals(True)
            self.data.pop(row)
            self.scenes.takeItem(row)
            self.scenes.setCurrentRow(min(row, len(self.data)-1))
            self.scenes.blockSignals(False)
            self.show_scene()
            self.save()

    def source_value(self, kind, initial=""):
        k = kind.lower()
        if "screen (display" in k or k == "screen" or "display capture" in k:
            screens = QtGui.QGuiApplication.screens()
            if not screens:
                return "Display 1"
            options = [f"Display {i+1}: {s.name()} ({s.geometry().width()}x{s.geometry().height()})" for i, s in enumerate(screens)]
            if len(options) > 1:
                choice, ok = QtWidgets.QInputDialog.getItem(self.window, "Select Display", "Choose screen to capture:", options, 0, False)
                return choice if ok else None
            return options[0]

        if "particular" in k or "window" in k:
            screens = QtGui.QGuiApplication.screens()
            options = [f"Monitor {i+1}: {s.name()} (Full Screen)" for i, s in enumerate(screens)]
            options.extend([
                "Active Window (Foreground Application)",
                "Specific Window Area (1280x720 center)",
                "Browser / Gaming Network App"
            ])
            choice, ok = QtWidgets.QInputDialog.getItem(self.window, "Select Window / Particular Screen", "Choose target window or screen region:", options, 0, False)
            return choice if ok else None

        if "video" in k or "media" in k:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.window, "Choose Video File", initial,
                "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v);;All Files (*.*)"
            )
            return path or None

        if "image" in k:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self.window, "Choose image", initial,
                "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
            if path and QtGui.QImage(path).isNull():
                QtWidgets.QMessageBox.warning(self.window, "Invalid image", "This image could not be loaded.")
                return None
            return path or None

        if "color" in k:
            color = QtWidgets.QColorDialog.getColor(QtGui.QColor(initial or "#F5B402"), self.window)
            return color.name() if color.isValid() else None

        # Text source
        value, ok = QtWidgets.QInputDialog.getMultiLineText(self.window, "Text source", "Text:", initial or "Your text")
        return value if ok else None

    def add_source(self):
        if not self.scene():
            return
        source_types = [
            "Screen (Display Capture)",
            "Particular Screen (Window Capture)",
            "Video (Media Source)",
            "Image",
            "Color",
            "Text",
        ]
        kind, ok = QtWidgets.QInputDialog.getItem(
            self.window, "Add Source", "Select source type to add to scene:",
            source_types, 0, False
        )
        if not ok:
            return

        k = kind.lower()
        if "screen (display" in k or k == "screen" or "display capture" in k:
            default_name = "Display capture"
            save_type = "Display Capture"
        elif "particular" in k or "window" in k:
            default_name = "Window capture"
            save_type = "Window Capture"
        elif "video" in k or "media" in k:
            default_name = "Video source"
            save_type = "Video"
        elif "image" in k:
            default_name = "Image"
            save_type = "Image"
        elif "color" in k:
            default_name = "Color"
            save_type = "Color"
        else:
            default_name = "Text"
            save_type = "Text"

        name = self.name("Name source", default_name, [s["name"] for s in self.scene()["sources"]])
        if not name:
            return
        value = self.source_value(kind)
        if value is not None:
            self.scene()["sources"].insert(0, {"name": name, "type": save_type, "value": value, "visible": True})
            self.show_scene()
            self.save()

    def edit_source(self):
        row = self.sources.currentIndex().row()
        if not self.scene() or row < 0:
            return
        source = self.scene()["sources"][row]
        value = self.source_value(source["type"], source["value"])
        if value is not None:
            source["value"] = value
            self.save()
            self.render()

    def rename_source(self):
        row = self.sources.currentIndex().row()
        if not self.scene() or row < 0:
            return
        sources = self.scene()["sources"]
        name = self.name("Rename source", sources[row]["name"], [s["name"] for i, s in enumerate(sources) if i != row])
        if name:
            sources[row]["name"] = name
            self.show_scene()
            self.sources.setCurrentIndex(self.model.index(row, 0))
            self.save()

    def remove_source(self):
        row = self.sources.currentIndex().row()
        if self.scene() and row >= 0 and self.confirm(self.scene()["sources"][row]["name"]):
            self.scene()["sources"].pop(row)
            self.show_scene()
            self.save()

    def visibility_changed(self, item):
        self.scene()["sources"][item.row()]["visible"] = item.checkState() == QtCore.Qt.CheckState.Checked
        self.save()
        self.render()

    def move_scene(self, delta):
        row = self.scenes.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < len(self.data):
            return
        self.data.insert(target, self.data.pop(row))
        self.scenes.blockSignals(True)
        self.scenes.insertItem(target, self.scenes.takeItem(row))
        self.scenes.setCurrentRow(target)
        self.scenes.blockSignals(False)
        self.show_scene()
        self.save()

    def move_source(self, delta):
        row = self.sources.currentIndex().row()
        sources = self.scene()["sources"] if self.scene() else []
        if row >= 0 and 0 <= row + delta < len(sources):
            sources.insert(row + delta, sources.pop(row))
            self.show_scene()
            self.sources.setCurrentIndex(self.model.index(row + delta, 0))
            self.save()

    def scene_menu(self, point):
        index = self.scenes.indexAt(point)
        if index.isValid():
            self.scenes.setCurrentRow(index.row())
        menu = QtWidgets.QMenu(self.window)
        menu.addAction("Create scene", self.add_scene)
        menu.addAction("Rename scene", self.rename_scene)
        menu.addAction("Remove scene", self.remove_scene)
        menu.exec(self.scenes.viewport().mapToGlobal(point))

    def source_menu(self, point):
        index = self.sources.indexAt(point)
        if index.isValid():
            self.sources.setCurrentIndex(index)
        menu = QtWidgets.QMenu(self.window)
        menu.addAction("Add source", self.add_source)
        menu.addAction("Properties", self.edit_source)
        menu.addAction("Rename source", self.rename_source)
        menu.addAction("Remove source", self.remove_source)
        menu.exec(self.sources.viewport().mapToGlobal(point))

    def render(self):
        scene = self.scene()
        if not scene:
            return
        self.window.findChild(QtWidgets.QLabel, "previewLabel").setText("PREVIEW  /  " + scene["name"])
        if not scene["sources"]:
            self.canvas.setPixmap(QtGui.QPixmap())
            self.canvas.setText('No sources in this scene\n\nClick + in Sources to add Screen, Window, Video, Image, Color, or Text.\nLive capture engine requires the compiled app.')
            return

        frame = QtGui.QPixmap(1280, 720)
        frame.fill(QtGui.QColor("#14171C"))
        painter = QtGui.QPainter(frame)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        cache_dir = self.path.parent / "media_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        for source in reversed(scene["sources"]):
            if not source.get("visible", True):
                continue
            stype = source["type"].lower()

            if "color" in stype:
                painter.fillRect(frame.rect(), QtGui.QColor(source["value"]))

            elif "image" in stype:
                image = QtGui.QImage(source["value"])
                if not image.isNull():
                    scaled = image.scaled(1280, 720, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                    painter.drawImage((1280 - scaled.width()) // 2, (720 - scaled.height()) // 2, scaled)

            elif "screen" in stype or "display capture" in stype:
                # Real Screen / Display Capture
                screens = QtGui.QGuiApplication.screens()
                screen_idx = 0
                val_lower = str(source.get("value", "")).lower()
                for i in range(len(screens)):
                    if f"display {i+1}" in val_lower or f"monitor {i+1}" in val_lower:
                        screen_idx = i
                        break
                screen = screens[screen_idx] if 0 <= screen_idx < len(screens) else QtGui.QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if not pixmap.isNull():
                        img = pixmap.toImage().scaled(1280, 720, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                        painter.drawImage((1280 - img.width()) // 2, (720 - img.height()) // 2, img)

                        # Studio watermark badge
                        painter.setPen(QtCore.Qt.PenStyle.NoPen)
                        painter.setBrush(QtGui.QColor(20, 24, 30, 190))
                        painter.drawRoundedRect(20, 20, 200, 30, 6, 6)
                        painter.setPen(QtGui.QColor("#F5B402"))
                        painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
                        painter.drawText(30, 40, f"DISPLAY CAPTURE · {screen.geometry().width()}x{screen.geometry().height()}")

            elif "particular" in stype or "window" in stype:
                # Particular Screen / Window Capture
                screens = QtGui.QGuiApplication.screens()
                screen = screens[0] if screens else QtGui.QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if not pixmap.isNull():
                        img = pixmap.toImage().scaled(1280, 720, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                        painter.drawImage((1280 - img.width()) // 2, (720 - img.height()) // 2, img)

                        # Window outline & header badge
                        painter.setPen(QtGui.QPen(QtGui.QColor("#F5B402"), 2))
                        painter.drawRect(2, 2, 1276, 716)

                        painter.setPen(QtCore.Qt.PenStyle.NoPen)
                        painter.setBrush(QtGui.QColor(20, 24, 30, 200))
                        painter.drawRoundedRect(20, 20, 260, 30, 6, 6)
                        painter.setPen(QtGui.QColor("#40C057"))
                        painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold))
                        val = str(source.get("value", "Window Capture"))
                        if len(val) > 28:
                            val = val[:26] + ".."
                        painter.drawText(30, 40, f"● WINDOW · {val}")

            elif "video" in stype or "media" in stype:
                # Video / Media Source
                video_path = source["value"]
                thumb_path = cache_dir / f"{Path(video_path).stem}_thumb.png" if video_path else None
                if thumb_path and not thumb_path.exists() and Path(video_path).exists():
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-ss", "00:00:01", "-i", video_path, "-frames:v", "1", "-update", "1", str(thumb_path)],
                            capture_output=True, timeout=5
                        )
                    except Exception:
                        pass

                has_thumb = thumb_path and thumb_path.exists() and not QtGui.QImage(str(thumb_path)).isNull()
                if has_thumb:
                    vimg = QtGui.QImage(str(thumb_path)).scaled(1280, 720, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                    painter.drawImage((1280 - vimg.width()) // 2, (720 - vimg.height()) // 2, vimg)
                else:
                    painter.fillRect(frame.rect(), QtGui.QColor("#101318"))
                    painter.setPen(QtGui.QColor("#F5B402"))
                    painter.setFont(QtGui.QFont("Segoe UI", 48, QtGui.QFont.Weight.Bold))
                    painter.drawText(frame.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "▶")

                # Sleek media player control bar at bottom
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QColor(18, 22, 28, 220))
                painter.drawRoundedRect(40, 640, 1200, 52, 8, 8)

                painter.setPen(QtGui.QColor("#F5B402"))
                painter.setFont(QtGui.QFont("Segoe UI", 13, QtGui.QFont.Weight.Bold))
                painter.drawText(60, 672, "▶")

                vname = Path(video_path).name if video_path else "Media Source"
                painter.setPen(QtGui.QColor("#F4F3EF"))
                painter.setFont(QtGui.QFont("Segoe UI", 11, QtGui.QFont.Weight.DemiBold))
                painter.drawText(85, 671, vname)

                painter.setPen(QtGui.QColor("#A5A9AE"))
                painter.setFont(QtGui.QFont("Segoe UI", 10))
                painter.drawText(1120, 671, "00:00 / 02:45")

                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QColor("#38404A"))
                painter.drawRoundedRect(85, 678, 1120, 4, 2, 2)
                painter.setBrush(QtGui.QColor("#F5B402"))
                painter.drawRoundedRect(85, 678, 320, 4, 2, 2)

            else:
                # Text Source
                painter.setPen(QtGui.QColor("white"))
                painter.setFont(QtGui.QFont("Segoe UI", 36, QtGui.QFont.Weight.DemiBold))
                painter.drawText(frame.rect().adjusted(40, 40, -40, -40),
                    QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap, source["value"])

        painter.end()
        self.canvas.setMinimumSize(1, 1)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored)
        self.canvas.setPixmap(frame.scaled(self.canvas.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
