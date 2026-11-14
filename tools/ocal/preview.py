"""Render the actual Qt Designer forms with Ocal styling, without the OBS engine.

Install PySide6-Essentials and Pillow, then run python tools/ocal/preview.py.
The preview uses illustrative source/mixer data and is not a recording app.
"""
import os
import sys
INTERACTIVE = "--interactive" in sys.argv
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if INTERACTIVE else "offscreen")
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

import PySide6
from PySide6 import QtCore, QtGui, QtWidgets, QtUiTools, QtSvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "build-ocal-preview"
OUTPUT.mkdir(exist_ok=True)
app = QtWidgets.QApplication([])
app.setStyle("Fusion")
QtCore.QDir.addSearchPath("theme", str(ROOT / "frontend/data/themes"))
for font in ["segoeui.ttf", "segoeuib.ttf", "segoeuisb.ttf"]:
    path = Path("C:/Windows/Fonts") / font
    if path.exists():
        QtGui.QFontDatabase.addApplicationFont(str(path))
app.setFont(QtGui.QFont("Segoe UI", 10))
rcc = Path(PySide6.__file__).parent / ("rcc.exe" if os.name == "nt" else "rcc")
subprocess.run([str(rcc), "--binary", str(ROOT / "frontend/forms/obs.qrc"),
                "-o", str(OUTPUT / "preview.rcc")], check=True)
assert QtCore.QResource.registerResource(str(OUTPUT / "preview.rcc"))

# Generate Windows icon from the editable vector asset.
icon = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_ARGB32)
icon.fill(QtCore.Qt.GlobalColor.transparent)
painter = QtGui.QPainter(icon)
QtSvg.QSvgRenderer(str(ROOT / "frontend/forms/images/ocal-record.svg")).render(painter)
painter.end()
icon.save(str(OUTPUT / "ocal-record.png"))
Image.open(OUTPUT / "ocal-record.png").save(
    ROOT / "frontend/cmake/windows/ocal-record.ico",
    sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)],
)

locale = dict(re.findall(r'^([^#\s=]+)="(.*)"$',
    (ROOT / "frontend/data/locale/en-US.ini").read_text(encoding="utf-8"), re.M))

def load_form(name):
    """Use Qt base widgets for OBS engine-backed widgets in this UI-only check."""
    root = ET.parse(ROOT / "frontend/forms" / name).getroot()
    custom = {c.findtext("class"): c.findtext("extends")
              for c in root.findall("./customwidgets/customwidget")}
    for widget in root.iter("widget"):
        widget.set("class", custom.get(widget.get("class"), widget.get("class")))
    for string in root.iter("string"):
        string.text = locale.get(string.text, string.text)
    for el in root.findall("resources") + root.findall("connections"):
        root.remove(el)
    buffer = QtCore.QBuffer()
    buffer.setData(ET.tostring(root))
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    loader = QtUiTools.QUiLoader()
    widget = loader.load(buffer)
    assert widget, loader.errorString()
    return widget

# Native OBS resolves the full inherited Yami stylesheet. This stand-alone
# harness uses a small Fusion baseline and the exact Ocal variant overrides.
base = (ROOT / "frontend/data/themes/Yami.obt").read_text(encoding="utf-8")
theme = (ROOT / "frontend/data/themes/Ocal.ovt").read_text(encoding="utf-8")
variables = dict(re.findall(r'(--[\w_]+):\s*([^;]+);', base + theme))
def resolve(match):
    value = variables.get(match[1], match[0])
    return re.sub(r'var\((--[\w_]+)\)', resolve, value)
qss = re.sub(r'@OBSTheme\w+\s*\{.*?\}', '', theme, flags=re.S)
qss = re.sub(r'var\((--[\w_]+)\)', resolve, qss)

app.setStyleSheet("""
QWidget {
    background-color: #1E2329;
    color: #F4F3EF;
    font-family: "Segoe UI", sans-serif;
}
QDockWidget > QWidget {
    background-color: #22272E;
}
QLabel {
    background: transparent;
}
""" + qss)

window = load_form("OBSBasic.ui")
window.setWindowTitle("Ocal Record — UI preview")
window.resize(1440, 900)
find = lambda name: window.findChild(QtCore.QObject, name)
find("previewDisabledWidget").hide()
find("previewXScrollBar").hide()
find("previewYScrollBar").hide()

# Match OBS's themed toolbar action icons in the standalone form loader.
icon_map = {
    "icon-plus": "plus", "icon-trash": "trash", "icon-gear": "settings",
    "icon-cogs": "settings", "icon-up": "up", "icon-down": "down",
    "icon-filter": "filter", "icon-minus": "minus"
}
for action in window.findChildren(QtGui.QAction):
    for cls in str(action.property("class") or "").split():
        if cls in icon_map:
            action.setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal" / f"{icon_map[cls]}.svg")))

find("previewLabel").setText("PREVIEW")
transitions_combo = find("transitions")
transitions_combo.clear()
transitions_combo.addItems(["Fade", "Cut", "Slide", "Fade to Black"])
find("transitionDuration").setValue(300)

# Themed icons for transitions dock and zoom toolbar
find("transitionAdd").setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/plus.svg")))
find("transitionRemove").setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/trash.svg")))
find("transitionProps").setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/settings.svg")))
find("previewZoomOutButton").setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/minus.svg")))
find("previewZoomInButton").setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/plus.svg")))

for widget in window.findChildren(QtWidgets.QLabel):
    if widget.text() == "TextLabel":
        widget.setText("Display capture")

scenes, sources = find("scenesDock"), find("sourcesDock")
mixer, transitions = find("mixerDock"), find("transitionsDock")
controls = load_form("OBSBasicControls.ui")
layout = controls.findChild(QtWidgets.QVBoxLayout, "buttonsVLayout")
layout.setContentsMargins(12, 12, 12, 12)
layout.setSpacing(6)

recording = controls.findChild(QtWidgets.QHBoxLayout, "recordingLayout")
recording_item = layout.takeAt(layout.indexOf(recording))
layout.insertItem(0, recording_item)

# Build a polished, unified Studio Brand card for the Controls dock
brand_card = QtWidgets.QFrame()
brand_card.setObjectName("brandHeaderContainer")
brand_layout = QtWidgets.QHBoxLayout(brand_card)
brand_layout.setContentsMargins(10, 8, 10, 8)
brand_layout.setSpacing(8)

logo_label = QtWidgets.QLabel()
logo_pixmap = QtGui.QPixmap(str(OUTPUT / "ocal-record.png")).scaled(
    22, 22, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation
)
logo_label.setPixmap(logo_pixmap)
brand_layout.addWidget(logo_label)

brand_title = QtWidgets.QLabel("Ocal Record")
brand_title.setObjectName("ocalBrand")
brand_layout.addWidget(brand_title)
brand_layout.addStretch()

brand_status = QtWidgets.QLabel("● READY")
brand_status.setObjectName("ocalBrandStatus")
brand_layout.addWidget(brand_status)

layout.insertWidget(0, brand_card)

# Wire icons for controls buttons
button_icons = {
    "recordButton": "record",
    "streamButton": "stream",
    "virtualCamButton": "camera",
    "virtualCamConfigButton": "settings",
    "modeSwitch": "studio",
    "settingsButton": "settings",
}
for btn_name, icon_name in button_icons.items():
    btn = controls.findChild(QtWidgets.QPushButton, btn_name)
    if btn:
        btn.setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal" / f"{icon_name}.svg")))
        btn.setIconSize(QtCore.QSize(16, 16))

# Quick session info card at bottom of controls
quick_info = QtWidgets.QFrame()
quick_info.setObjectName("controlQuickInfo")
info_layout = QtWidgets.QVBoxLayout(quick_info)
info_layout.setContentsMargins(10, 8, 10, 8)
info_layout.setSpacing(3)
info_title = QtWidgets.QLabel("OUTPUT PROFILE")
info_title.setStyleSheet("color: #79818C; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;")
info_desc = QtWidgets.QLabel("1080p60 · NVENC H.264 · MKV/MP4")
info_desc.setStyleSheet("color: #C8CBD0; font-size: 11px; font-weight: 500;")
info_layout.addWidget(info_title)
info_layout.addWidget(info_desc)
layout.addWidget(quick_info)
layout.addStretch()

for name in ["broadcastButton", "pauseRecordButton", "replayBufferButton", "saveReplayButton"]:
    w = controls.findChild(QtWidgets.QWidget, name)
    if w:
        w.hide()

dock = QtWidgets.QDockWidget("Capture", window)
dock.setObjectName("controlsDock")
dock.setWidget(controls)

window.setCorner(QtCore.Qt.Corner.BottomLeftCorner, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
window.setCorner(QtCore.Qt.Corner.BottomRightCorner, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
window.addDockWidget(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea, scenes)
window.splitDockWidget(scenes, sources, QtCore.Qt.Orientation.Horizontal)
window.splitDockWidget(sources, mixer, QtCore.Qt.Orientation.Horizontal)
window.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
window.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, transitions)
window.splitDockWidget(dock, transitions, QtCore.Qt.Orientation.Vertical)
window.resizeDocks([dock], [290], QtCore.Qt.Orientation.Horizontal)
window.resizeDocks([scenes, sources, mixer], [230, 270, 450], QtCore.Qt.Orientation.Horizontal)
window.resizeDocks([scenes, sources, mixer], [260, 260, 260], QtCore.Qt.Orientation.Vertical)
window.resizeDocks([dock, transitions], [460, 260], QtCore.Qt.Orientation.Vertical)

find("scenes").addItems(["Screen recording", "Camera + screen", "Starting soon"])
find("scenes").setCurrentRow(0)
model = QtGui.QStandardItemModel()
for label_text in ["Display capture", "Webcam", "Microphone"]:
    model.appendRow(QtGui.QStandardItem(label_text))
find("sources").setModel(model)

preview = find("preview")
preview.setStyleSheet("background: #14171C; border: 1px solid #2F353E;")
preview_layout = QtWidgets.QVBoxLayout(preview)
label = QtWidgets.QLabel("Your next great recording starts here\n\nUI preview · Capture engine is not running")
label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
label.setStyleSheet("color: #A5A9AE; font-size: 16px; border: 0;")
preview_layout.addWidget(label)

audio = QtWidgets.QWidget()
audio_layout = QtWidgets.QVBoxLayout(audio)
audio_layout.setContentsMargins(12, 12, 12, 12)
audio_layout.setSpacing(8)
for name, value in [("Desktop audio", 68), ("Microphone", 43)]:
    audio_layout.addWidget(QtWidgets.QLabel(name))
    meter = QtWidgets.QProgressBar()
    meter.setValue(value)
    meter.setTextVisible(False)
    meter.setFixedHeight(6)
    meter.setStyleSheet("QProgressBar {background: #2D333B; border-radius: 3px; border: 0;} QProgressBar::chunk {background: #F5B402; border-radius: 3px;}")
    audio_layout.addWidget(meter)
    slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setValue(80)
    slider.setFixedHeight(20)
    audio_layout.addWidget(slider)
    audio_layout.addSpacing(6)
audio_layout.addStretch()
mixer.setWidget(audio)
window.statusBar().showMessage("UI PREVIEW     •     Ocal Record                                              1920 × 1080   /   60 FPS")

# Interactive state controllers
record_btn = controls.findChild(QtWidgets.QPushButton, "recordButton")
stream_btn = controls.findChild(QtWidgets.QPushButton, "streamButton")
vcam_btn = controls.findChild(QtWidgets.QPushButton, "virtualCamButton")
mode_btn = controls.findChild(QtWidgets.QPushButton, "modeSwitch")
settings_btn = controls.findChild(QtWidgets.QPushButton, "settingsButton")

# Recording configuration and process management
recordings_dir = Path.home() / "Videos" / "Ocal_Recordings"
try:
    recordings_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    recordings_dir = OUTPUT / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

recording_process = None
current_recording_file = None
recording_state = {"active": False, "seconds": 0}
record_timer = QtCore.QTimer(window)

# Animated audio mixer level simulation
audio_meters_timer = QtCore.QTimer(window)
import random
meters = audio.findChildren(QtWidgets.QProgressBar)
def animate_audio():
    if len(meters) >= 2:
        if recording_state["active"]:
            meters[0].setValue(random.randint(60, 95))
            meters[1].setValue(random.randint(40, 80))
        else:
            meters[0].setValue(random.randint(20, 50))
            meters[1].setValue(random.randint(15, 35))
audio_meters_timer.timeout.connect(animate_audio)
audio_meters_timer.start(120)

def update_record_timer():
    recording_state["seconds"] += 1
    s = recording_state["seconds"]
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    time_str = f"{h:02d}:{m:02d}:{sec:02d}"
    brand_status.setText(f"● REC [{time_str}]")
    fname = current_recording_file.name if current_recording_file else "recording.mp4"
    window.statusBar().showMessage(f"● RECORDING  [{time_str}]  •  {fname}  •  1920 × 1080 / 30 FPS")

record_timer.timeout.connect(update_record_timer)

def toggle_recording():
    global recording_process, current_recording_file
    recording_state["active"] = not recording_state["active"]
    if recording_state["active"]:
        recording_state["seconds"] = 0
        from datetime import datetime
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        current_recording_file = recordings_dir / f"Ocal_Record_{stamp}.mp4"

        # Launch real FFmpeg Windows Desktop Screen Recording
        cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", "30",
            "-i", "desktop",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(current_recording_file)
        ]
        try:
            recording_process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as err:
            recording_process = None
            print("FFmpeg recording launch error:", err)

        record_btn.setProperty("class", "state-active")
        record_btn.setText("Stop Recording")
        record_btn.setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/stop.svg")))
        record_btn.style().unpolish(record_btn)
        record_btn.style().polish(record_btn)
        brand_status.setText("● REC [00:00:00]")
        brand_status.setStyleSheet("color: #FA5252; font-weight: 700; font-size: 11px;")
        record_timer.start(1000)
        window.statusBar().showMessage(f"● RECORDING STARTED  •  Saving to {current_recording_file.name}")
    else:
        record_timer.stop()
        if recording_process:
            try:
                recording_process.communicate(b'q', timeout=4)
            except Exception:
                recording_process.terminate()
                recording_process.wait()
            recording_process = None

        record_btn.setProperty("class", "")
        record_btn.setText("Start Recording")
        record_btn.setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/record.svg")))
        record_btn.style().unpolish(record_btn)
        record_btn.style().polish(record_btn)
        brand_status.setText("● READY")
        brand_status.setStyleSheet("color: #F5B402; font-weight: 600; font-size: 11px;")

        if current_recording_file and current_recording_file.exists():
            size_mb = current_recording_file.stat().st_size / (1024 * 1024)
            window.statusBar().showMessage(f"✓ Saved: {current_recording_file.name} ({size_mb:.2f} MB) in Videos/Ocal_Recordings")

            if INTERACTIVE:
                box = QtWidgets.QMessageBox(window)
                box.setWindowTitle("Recording Saved — Ocal Record")
                box.setText(f"<b>Recording Saved Successfully!</b><br><br>"
                            f"<b>File:</b> {current_recording_file.name}<br>"
                            f"<b>Size:</b> {size_mb:.2f} MB<br>"
                            f"<b>Location:</b> {recordings_dir}")
                open_btn = box.addButton("Open Folder", QtWidgets.QMessageBox.ButtonRole.ActionRole)
                play_btn = box.addButton("Play Video", QtWidgets.QMessageBox.ButtonRole.ActionRole)
                box.addButton("Close", QtWidgets.QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() == open_btn:
                    os.startfile(str(recordings_dir))
                elif box.clickedButton() == play_btn:
                    os.startfile(str(current_recording_file))
        else:
            window.statusBar().showMessage("Ready")

record_btn.clicked.connect(toggle_recording)

# Connect File -> Show Recordings to open folder
action_show_rec = window.findChild(QtGui.QAction, "actionShowRecordings")
if action_show_rec:
    action_show_rec.setEnabled(True)
    action_show_rec.triggered.connect(lambda: os.startfile(str(recordings_dir)))

def toggle_streaming():
    if stream_btn.text() == "Start Streaming":
        stream_btn.setText("Stop Streaming")
        stream_btn.setStyleSheet("background: #2E4B33; border-color: #40C057; color: #FFFFFF;")
        window.statusBar().showMessage("LIVE STREAMING • Bitrate: 6000 kbps • 60 FPS")
    else:
        stream_btn.setText("Start Streaming")
        stream_btn.setStyleSheet("")
        window.statusBar().showMessage("Stream stopped • Ready")

stream_btn.clicked.connect(toggle_streaming)

def show_settings_dialog():
    dialog = QtWidgets.QDialog(window)
    dialog.setWindowTitle("Ocal Record Settings")
    dialog.resize(480, 360)
    d_layout = QtWidgets.QVBoxLayout(dialog)
    d_layout.setContentsMargins(18, 18, 18, 18)
    d_layout.setSpacing(12)

    title = QtWidgets.QLabel("Recording & Video Settings")
    title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F5B402;")
    d_layout.addWidget(title)

    form = QtWidgets.QFormLayout()
    form.setSpacing(10)
    base_res = QtWidgets.QComboBox()
    base_res.addItems(["1920x1080 (16:9)", "2560x1440 (16:9)", "3840x2160 (4K)", "1280x720 (16:9)"])
    fps_box = QtWidgets.QComboBox()
    fps_box.addItems(["60 FPS", "59.94 FPS", "30 FPS", "120 FPS"])
    enc_box = QtWidgets.QComboBox()
    enc_box.addItems(["NVIDIA NVENC H.264 (recommended)", "AMD HW H.264", "Intel QuickSync", "x264 (Software)"])
    fmt_box = QtWidgets.QComboBox()
    fmt_box.addItems(["MKV (Crash-safe)", "MP4", "MOV", "FLV"])

    form.addRow("Base Canvas Resolution:", base_res)
    form.addRow("Common FPS Values:", fps_box)
    form.addRow("Video Encoder:", enc_box)
    form.addRow("Recording Format:", fmt_box)
    d_layout.addLayout(form)

    d_layout.addStretch()
    btn_box = QtWidgets.QHBoxLayout()
    btn_box.addStretch()
    ok_btn = QtWidgets.QPushButton("Done")
    ok_btn.setStyleSheet("background: #F5B402; color: #14181D; font-weight: 700; min-width: 80px; padding: 6px 14px;")
    ok_btn.clicked.connect(dialog.accept)
    btn_box.addWidget(ok_btn)
    d_layout.addLayout(btn_box)
    dialog.exec()

settings_btn.clicked.connect(show_settings_dialog)
settings_action = window.findChild(QtGui.QAction, "action_Settings")
if settings_action:
    settings_action.triggered.connect(show_settings_dialog)

# Transitions interactivity
def add_transition():
    text, ok = QtWidgets.QInputDialog.getText(window, "Add Transition", "Transition name:")
    if ok and text.strip():
        transitions_combo.addItem(text.strip())
        transitions_combo.setCurrentText(text.strip())

def remove_transition():
    if transitions_combo.count() > 1:
        transitions_combo.removeItem(transitions_combo.currentIndex())

find("transitionAdd").clicked.connect(add_transition)
find("transitionRemove").clicked.connect(remove_transition)
find("transitionProps").clicked.connect(lambda: QtWidgets.QMessageBox.information(
    window, "Transition Properties", f"Type: {transitions_combo.currentText()}\nDuration: {find('transitionDuration').value()} ms"
))

# Zoom controls interactivity
zoom_pct_label = find("previewScalePercent")
scale_combo = find("previewScalingMode")

def zoom_in():
    val = int(zoom_pct_label.text().replace("%", ""))
    val = min(val + 25, 400)
    zoom_pct_label.setText(f"{val}%")

def zoom_out():
    val = int(zoom_pct_label.text().replace("%", ""))
    val = max(val - 25, 25)
    zoom_pct_label.setText(f"{val}%")

find("previewZoomInButton").clicked.connect(zoom_in)
find("previewZoomOutButton").clicked.connect(zoom_out)

window.show()
app.processEvents()

if INTERACTIVE:
    from workspace import Workspace
    workspace = Workspace(window, label, OUTPUT / "workspace.json")
    window.setWindowIcon(QtGui.QIcon(str(ROOT / "frontend/forms/images/ocal-record.svg")))
    window.statusBar().showMessage("Ocal Record UI Ready — Click 'Start Recording' to test recording state, edit scenes/sources on the left, or adjust transitions on the right.")
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())

window.grab().save(str(OUTPUT / "ocal-record-preview.png"))

# Active recording state updates
button = controls.findChild(QtWidgets.QPushButton, "recordButton")
assert button.isVisible() and button.width() >= 100
button.setProperty("class", "state-active")
button.setText("Stop Recording")
button.setIcon(QtGui.QIcon(str(ROOT / "frontend/data/themes/Ocal/stop.svg")))
button.style().unpolish(button)
button.style().polish(button)
brand_status.setText("● REC")
brand_status.setStyleSheet("color: #FA5252; font-weight: 700; font-size: 11px;")
app.processEvents()
window.grab().save(str(OUTPUT / "ocal-record-active.png"))

window.resize(1100, 720)
app.processEvents()
assert button.isVisible() and button.width() >= 100
window.grab().save(str(OUTPUT / "ocal-record-compact.png"))
print(f"Qt form rendering and primary control checks passed. Preview: {OUTPUT}")

if "--test-workspace" in sys.argv:
    from workspace import Workspace
    from unittest.mock import patch
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "workspace.json"
        editor = Workspace(window, label, path)
        with patch.object(QtWidgets.QInputDialog, "getText", return_value=("Gameplay", True)):
            find("actionAddScene").trigger()
        assert len(editor.data) == 2 and editor.scene()["name"] == "Gameplay"
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("Text", True)), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Title", True)), \
             patch.object(QtWidgets.QInputDialog, "getMultiLineText", return_value=("Hello Ocal", True)):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["value"] == "Hello Ocal"
        assert not label.pixmap().isNull()
        editor.model.item(0).setCheckState(QtCore.Qt.CheckState.Unchecked)
        assert editor.scene()["sources"][0]["visible"] is False
        editor.scenes.setCurrentRow(0)
        assert editor.model.rowCount() == 0
        editor.scenes.setCurrentRow(1)
        assert editor.model.rowCount() == 1
        image_path = Path(temporary) / "sample.png"
        sample = QtGui.QImage(32, 32, QtGui.QImage.Format.Format_RGB32)
        sample.fill(QtGui.QColor("#F5B402"))
        sample.save(str(image_path))
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("Image", True)), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Picture", True)), \
             patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(image_path), "")):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["type"] == "Image"
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("Color", True)), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Background", True)), \
             patch.object(QtWidgets.QColorDialog, "getColor", return_value=QtGui.QColor("#123456")):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["value"] == "#123456"
        find("actionSourceDown").trigger()
        assert editor.scene()["sources"][1]["name"] == "Background"
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.StandardButton.Yes):
            find("actionRemoveSource").trigger()
            find("actionRemoveSource").trigger()
        assert editor.model.rowCount() == 1
        with patch.object(QtWidgets.QInputDialog, "getText", return_value=("Intro", True)):
            editor.rename_scene()
        with patch.object(QtWidgets.QInputDialog, "getMultiLineText", return_value=("Edited", True)):
            find("actionSourceProperties").trigger()
        assert editor.scene()["sources"][0]["value"] == "Edited"
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("Text", False)):
            find("actionAddSource").trigger()
        assert editor.model.rowCount() == 1

        # Test adding Screen (Display Capture), Particular Screen (Window Capture), and Video (Media Source)
        with patch.object(QtWidgets.QInputDialog, "getItem", side_effect=[("Screen (Display Capture)", True), ("Display 1: Primary (1920x1080)", True)]), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Main Display", True)):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["type"] == "Display Capture"

        with patch.object(QtWidgets.QInputDialog, "getItem", side_effect=[("Particular Screen (Window Capture)", True), ("Active Window", True)]), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Game Window", True)):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["type"] == "Window Capture"

        sample_video = ROOT / "build-ocal-preview/test_sample.mp4"
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("Video (Media Source)", True)), \
             patch.object(QtWidgets.QInputDialog, "getText", return_value=("Gameplay Video", True)), \
             patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(sample_video), "")):
            find("actionAddSource").trigger()
        assert editor.scene()["sources"][0]["type"] == "Video"
        assert editor.model.rowCount() == 4
        assert not label.pixmap().isNull()

        find("actionSceneUp").trigger()
        assert editor.data[0]["name"] == "Intro"
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == editor.data
        # Reload the saved model through the same loader used on application startup.
        reloaded_window = load_form("OBSBasic.ui")
        reloaded = Workspace(reloaded_window, QtWidgets.QLabel(), path)
        assert reloaded.data == saved
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.StandardButton.Yes):
            while editor.model.rowCount() > 0:
                find("actionRemoveSource").trigger()
            assert editor.model.rowCount() == 0
            find("actionRemoveScene").trigger()
        assert len(editor.data) == 1
        print("PASS: toolbar creation, independent scenes, text rendering, visibility, rename, properties, cancel, reorder, save/reload, and removal")
