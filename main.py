import sys
import threading
import numpy as np
import cv2
import pyautogui
import mss
from PyQt5 import QtWidgets, QtCore, QtGui
import os

# ---------- ATTACH TO FORTNITE PROCESS ----------
import psutil

def get_fortnite_window_rect():
    """
    Try to find the window rect of 'FortniteClient-Win64-Shipping.exe'.
    Returns (left, top, right, bottom) if found, otherwise None.
    """
    try:
        import win32gui
        import win32process
    except ImportError:
        print("win32gui/win32process modules not installed, cannot attach to Fortnite window.")
        return None

    hwnd_hwnd = []

    def enum_window_callback(hwnd, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['pid'] == pid and proc.info['name'] == "FortniteClient-Win64-Shipping.exe":
                    hwnd_hwnd.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(enum_window_callback, None)

    for hwnd in hwnd_hwnd:
        if win32gui.IsWindowVisible(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            return rect
    return None

# --------- AI Helper for snap aim using OpenCV and mediapipe ---------
# Placeholder for AI assistance - this uses classical computer vision for proof; ML can be integrated here.

class AimbotAIHelper:
    def __init__(self, snap_strength='Medium'):
        # Snap strength can be 'Weak', 'Medium', or 'Strong'
        self.snap_strength = snap_strength
        self.preset_params = {
            'Weak': 0.25,   # lowest magnetic snap/assist
            'Medium': 0.1,  # normal
            'Strong': 0.01  # ultra-strong instant snap
        }

    def set_snap_strength(self, preset):
        assert preset in self.preset_params
        self.snap_strength = preset

    def calculate_snap_duration(self):
        """Return the duration param for pyautogui.moveTo."""
        return self.preset_params.get(self.snap_strength, 0.1)

    def smart_snap_to_target(self, target_x, target_y):
        """Move the mouse to target with selected snap strength preset."""
        screen_x, screen_y = pyautogui.position()
        duration = self.calculate_snap_duration()
        pyautogui.moveTo(target_x, target_y, duration=duration)

class AimbotDebugger(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hardcore Fortnite Debugger Window")
        self.setGeometry(200, 200, 340, 220)
        self.aimbot_enabled = False

        # Try to attach to Fortnite client window
        self.fortnite_rect = get_fortnite_window_rect()
        if self.fortnite_rect is None:
            QtWidgets.QMessageBox.warning(
                self, "Fortnite Not Found",
                "FortniteClient-Win64-Shipping.exe window not found. The aimbot will use the primary monitor center area."
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "Fortnite Found",
                "Attached to FortniteClient-Win64-Shipping.exe window."
            )

        # Check if the target template file exists and is loaded correctly
        template_path = 'target.png'
        if not os.path.exists(template_path):
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Could not find {template_path}. Place the file in the app directory.")
            self.target_template = None
        else:
            self.target_template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
            if self.target_template is None:
                QtWidgets.QMessageBox.critical(
                    self, "Error", f"Unable to load {template_path}. File may be corrupt or unusable.")

        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        # Timer for updating info
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.repaint)
        self.timer.start(50)

        self.layout = QtWidgets.QVBoxLayout()
        self.status_label = QtWidgets.QLabel('Aimbot: OFF')
        self.status_label.setStyleSheet('font-size: 20px; color: red;')

        self.toggle_btn = QtWidgets.QPushButton("Enable Aimbot")
        self.toggle_btn.clicked.connect(self.toggle_aimbot)

        # Snap preset selector (new)
        self.preset_label = QtWidgets.QLabel("Snap Strength Preset:")
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(['Weak', 'Medium', 'Strong'])
        self.preset_combo.setCurrentText('Medium')
        self.preset_combo.currentTextChanged.connect(self.preset_changed)

        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.toggle_btn)
        self.layout.addWidget(self.preset_label)
        self.layout.addWidget(self.preset_combo)
        self.setLayout(self.layout)

        # AI helper for aimbot snap strength presets
        self.aimbot_ai = AimbotAIHelper(self.preset_combo.currentText())

        self.aim_thread = threading.Thread(target=self.run_aimbot, daemon=True)
        self.aim_thread.start()

    def preset_changed(self, preset):
        # Update AI snap preset for aimbot
        self.aimbot_ai.set_snap_strength(preset)

    def toggle_aimbot(self):
        self.aimbot_enabled = not self.aimbot_enabled
        if self.aimbot_enabled:
            self.status_label.setText('Aimbot: ON')
            self.status_label.setStyleSheet('font-size: 20px; color: green;')
            self.toggle_btn.setText("Disable Aimbot")
        else:
            self.status_label.setText('Aimbot: OFF')
            self.status_label.setStyleSheet('font-size: 20px; color: red;')
            self.toggle_btn.setText("Enable Aimbot")

    def run_aimbot(self):
        with mss.mss() as sct:
            # Attach to Fortnite if possible
            if self.fortnite_rect is not None:
                left, top, right, bottom = self.fortnite_rect
                w = right - left
                h = bottom - top
                # Scan a region inside the game window
                region_w = min(800, w)
                region_h = min(600, h)
                region_left = left + (w - region_w)//2
                region_top = top + (h - region_h)//2
                sct_area = {'top': region_top, 'left': region_left, 'width': region_w, 'height': region_h}
            else:
                monitor = sct.monitors[1]
                w, h = 800, 600  # Area to scan (adjust as needed)
                left, top = (monitor['width'] - w) // 2, (monitor['height'] - h) // 2
                sct_area = {'top': top, 'left': left, 'width': w, 'height': h}
            template = self.target_template

            # Fix: Only proceed if the template has been successfully loaded
            if template is None:
                print("Error: target.png could not be loaded or found. Make sure the file exists and is a valid image.")
                return

            temp_h, temp_w = template.shape[:2]

            # ---- PLAYER BODY DETECTION HELPER INIT ----
            self.previous_frame_bodies = None  # For tracking movement

            while True:
                if not self.aimbot_enabled:
                    QtCore.QThread.msleep(30)
                    continue

                scr = np.array(sct.grab(sct_area))
                img = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)

                # --- Simulated body detection: use color thresholding, contour, etc.
                # In Fortnite, bodies might have a defined color/outline. For demo, look for non-background moving objects.
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (9, 9), 0)
                _, thresh = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                moving_bodies = []
                min_body_area = 320  # Filter small objects

                current_frame_bodies = []
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    if area > min_body_area:
                        x, y, w_cnt, h_cnt = cv2.boundingRect(cnt)
                        current_frame_bodies.append((x, y, w_cnt, h_cnt))
                
                # Compare to previous detections for movement
                if self.previous_frame_bodies is not None:
                    for curr in current_frame_bodies:
                        for prev in self.previous_frame_bodies:
                            x_prev, y_prev, w_prev, h_prev = prev
                            x_curr, y_curr, w_curr, h_curr = curr
                            # Simple movement check
                            if abs(x_curr - x_prev) > 10 or abs(y_curr - y_prev) > 10:
                                moving_bodies.append(curr)
                self.previous_frame_bodies = current_frame_bodies.copy()

                # Draw and log moving body rectangles for debugging
                for (x, y, w_cnt, h_cnt) in moving_bodies:
                    cv2.rectangle(img, (x, y), (x+w_cnt, y+h_cnt), (0, 255, 255), 2)
                    print(f"Detected moving fortnite_player_body at ({x}, {y}, {w_cnt}, {h_cnt}) in scan area.")

                # Continue with template matching for aimbot
                res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                threshold = 0.72

                # -------- SNAP AIM LOGIC w/ AI PRESET ---------
                # Use AI to snap onto the best body if found on screen and template matches on it
                snap_candidate = None
                if max_val > threshold:
                    if self.fortnite_rect is not None:
                        region_left = sct_area['left']
                        region_top = sct_area['top']
                        candidate_x = region_left + max_loc[0] + temp_w // 2
                        candidate_y = region_top + max_loc[1] + temp_h // 2
                    else:
                        candidate_x = sct_area['left'] + max_loc[0] + temp_w // 2
                        candidate_y = sct_area['top'] + max_loc[1] + temp_h // 2
                    
                    # Only snap if template overlaps some moving/contour rectangle (player body)
                    for (x, y, w_cnt, h_cnt) in moving_bodies:
                        if (candidate_x >= sct_area['left'] + x and candidate_x <= sct_area['left'] + x + w_cnt and
                            candidate_y >= sct_area['top'] + y and candidate_y <= sct_area['top'] + y + h_cnt):
                            snap_candidate = (candidate_x, candidate_y)
                            break

                if snap_candidate is not None:
                    # AI-enhanced snap aim: uses selected preset
                    self.aimbot_ai.smart_snap_to_target(snap_candidate[0], snap_candidate[1])

                QtCore.QThread.msleep(20)

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = AimbotDebugger()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()