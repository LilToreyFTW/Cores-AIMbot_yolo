"""
Fortnite Master GUI Aim Snap System
====================================
A professional, highly configurable, and feature-rich aim assistance tool for Fortnite.

Features:
- Modern PyQt5 GUI with dark theme
- Hybrid detection system (template, color, contour, movement, optional YOLO)
- Humanized snapping with bezier curves
- FOV overlay with visual feedback
- Multi-threaded screen capture
- Hotkey support
- Performance monitoring
- Anti-detection considerations

Installation:
pip install PyQt5 numpy opencv-python mss pyautogui psutil pynput keyboard

Usage:
python aim_snap_master.py
"""

import sys
import json
import os
import time
import random
import logging
import threading
import math
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
import cv2
import mss
import pyautogui
import psutil

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeySequence

from pynput import mouse, keyboard

# AI Detection imports (optional - will fail gracefully if not installed)
try:
    import torch
    from ultralytics import YOLO
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("PyTorch/ULtralytics not installed - AI detection disabled")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aim_snap.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== CONFIGURATION ====================

class SnapPreset(Enum):
    """Snap strength presets with humanized parameters."""
    WEAK = "Weak"
    MEDIUM = "Medium"
    STRONG = "Strong"
    INSTANT = "Instant"


class TargetPriority(Enum):
    """Target selection priority."""
    HEAD = "Head"
    UPPER_BODY = "Upper Body"
    CENTER_MASS = "Center Mass"
    NEAREST = "Nearest"


class AimMode(Enum):
    """Aim operation modes."""
    AIM_ASSIST = "Aim Assist"
    TRIGGER_BOT = "Trigger Bot"


@dataclass
class SnapPresetConfig:
    """Configuration for a snap preset."""
    duration: float
    smoothing: float
    acceleration: float
    curve_power: float
    randomization: float


@dataclass
class Config:
    """Main configuration class with JSON save/load support."""
    # General settings
    enabled: bool = False
    aim_mode: str = AimMode.AIM_ASSIST.value
    snap_preset: str = SnapPreset.MEDIUM.value
    target_priority: str = TargetPriority.NEAREST.value
    
    # FOV settings
    fov_size: int = 150
    show_fov_overlay: bool = True
    
    # Detection settings
    template_threshold: float = 0.72
    enable_color_detection: bool = True
    enable_contour_detection: bool = True
    enable_movement_detection: bool = True
    enable_yolo: bool = True  # Enabled by default for RTX 5070 users
    yolo_model: str = "yolov8n.pt"  # Default to nano model for speed
    yolo_confidence: float = 0.5
    yolo_use_gpu: bool = True  # Use GPU acceleration
    min_body_area: int = 320
    
    # Color filter (Fortnite skin tones - RGB)
    color_filter_lower: List[int] = None
    color_filter_upper: List[int] = None
    
    # Hotkey settings
    activation_key: str = "mouse_right"  # Hold to snap aim
    toggle_key: str = "p"  # Toggle aimbot on/off
    
    # Anti-detection
    random_delay_min: float = 0.0
    random_delay_max: float = 0.05
    humanization_factor: float = 0.3
    
    # Performance
    detection_fps_limit: int = 60
    debug_mode: bool = False
    
    # Window settings
    minimize_to_tray: bool = False
    window_opacity: float = 0.95
    
    def __post_init__(self):
        """Initialize default values for lists."""
        if self.color_filter_lower is None:
            # Default Fortnite skin tone range (adjust as needed)
            self.color_filter_lower = [100, 80, 60]
        if self.color_filter_upper is None:
            self.color_filter_upper = [180, 150, 130]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create Config from dictionary."""
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Config to dictionary."""
        return asdict(self)
    
    def save(self, filepath: str = "aim_snap_config.json") -> bool:
        """Save configuration to JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.to_dict(), f, indent=4)
            logger.info(f"Configuration saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    @classmethod
    def load(cls, filepath: str = "aim_snap_config.json") -> 'Config':
        """Load configuration from JSON file."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                logger.info(f"Configuration loaded from {filepath}")
                return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
        return cls()


# Preset configurations
SNAP_PRESETS: Dict[str, SnapPresetConfig] = {
    SnapPreset.WEAK.value: SnapPresetConfig(
        duration=0.25,
        smoothing=0.8,
        acceleration=0.5,
        curve_power=2.0,
        randomization=0.15
    ),
    SnapPreset.MEDIUM.value: SnapPresetConfig(
        duration=0.15,
        smoothing=0.5,
        acceleration=0.7,
        curve_power=3.0,
        randomization=0.10
    ),
    SnapPreset.STRONG.value: SnapPresetConfig(
        duration=0.08,
        smoothing=0.3,
        acceleration=0.85,
        curve_power=4.0,
        randomization=0.05
    ),
    SnapPreset.INSTANT.value: SnapPresetConfig(
        duration=0.02,
        smoothing=0.1,
        acceleration=0.95,
        curve_power=5.0,
        randomization=0.02
    ),
}


# ==================== UTILITY FUNCTIONS ====================

def get_fortnite_window_rect() -> Optional[Tuple[int, int, int, int]]:
    """
    Try to find the window rect of 'FortniteClient-Win64-Shipping.exe'.
    Returns (left, top, right, bottom) if found, otherwise None.
    """
    try:
        import win32gui
        import win32process
    except ImportError:
        logger.warning("win32gui/win32process modules not installed")
        return None
    
    hwnd_list = []
    
    def enum_window_callback(hwnd, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['pid'] == pid and proc.info['name'] == "FortniteClient-Win64-Shipping.exe":
                    hwnd_list.append(hwnd)
        except Exception:
            pass
        return True
    
    try:
        win32gui.EnumWindows(enum_window_callback, None)
        
        for hwnd in hwnd_list:
            if win32gui.IsWindowVisible(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
                logger.info(f"Found Fortnite window at {rect}")
                return rect
    except Exception as e:
        logger.error(f"Error finding Fortnite window: {e}")
    
    return None


def bezier_easing(t: float, power: float) -> float:
    """
    Bezier-like easing function for humanized movement.
    t: progress (0.0 to 1.0)
    power: curve strength (higher = more acceleration at end)
    """
    if power <= 0:
        return t
    return t ** power


def apply_randomization(value: float, factor: float) -> float:
    """Apply randomization to a value for anti-detection."""
    if factor <= 0:
        return value
    random_offset = (random.random() - 0.5) * 2 * factor * value
    return value + random_offset


# ==================== DETECTION ENGINE ====================

class DetectionEngine(QThread):
    """
    Multi-threaded detection engine with hybrid detection methods.
    Supports template matching, color detection, contour detection, and movement tracking.
    """
    frame_ready = pyqtSignal(np.ndarray, dict)
    target_detected = pyqtSignal(dict)
    performance_stats = pyqtSignal(dict)
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.running = False
        self.paused = False
        self.fortnite_rect = get_fortnite_window_rect()
        self.template = None
        self.previous_frame = None
        self.previous_bodies = []
        self.frame_count = 0
        self.detection_times = []
        self.fps = 0
        self.activation_key_pressed = False
        
        # YOLO model for AI detection
        self.yolo_model = None
        if AI_AVAILABLE and self.config.enable_yolo:
            self.load_yolo_model()
        
        # Load template
        self.load_template()
        
        # Screen capture setup
        self.sct = mss.mss()
        self.capture_area = self.setup_capture_area()
    
    def load_yolo_model(self):
        """Load YOLO model for AI-based detection."""
        try:
            if not AI_AVAILABLE:
                logger.warning("AI dependencies not available - YOLO detection disabled")
                return
            
            # Check if CUDA is available for GPU acceleration
            if self.config.yolo_use_gpu and torch.cuda.is_available():
                device = 'cuda'
                logger.info(f"Using GPU acceleration for YOLO (CUDA available)")
            else:
                device = 'cpu'
                logger.info(f"Using CPU for YOLO detection")
            
            # Load YOLO model (will auto-download if not present)
            model_path = self.config.yolo_model
            self.yolo_model = YOLO(model_path)
            self.yolo_model.to(device)
            
            logger.info(f"YOLO model loaded: {model_path} on device: {device}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.yolo_model = None
    
    def set_activation_key_state(self, pressed: bool):
        """Set the activation key state (pressed/released)."""
        self.activation_key_pressed = pressed
    
    def load_template(self) -> bool:
        """Load target template image."""
        template_path = 'target.png'
        try:
            if os.path.exists(template_path):
                self.template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
                if self.template is not None:
                    logger.info(f"Template loaded: {self.template.shape}")
                    return True
                else:
                    logger.error("Failed to load template image")
            else:
                logger.warning(f"Template file not found: {template_path}")
        except Exception as e:
            logger.error(f"Error loading template: {e}")
        return False
    
    def setup_capture_area(self) -> dict:
        """Setup screen capture area based on Fortnite window or primary monitor."""
        if self.fortnite_rect:
            left, top, right, bottom = self.fortnite_rect
            w = right - left
            h = bottom - top
            # Scan region inside game window
            region_w = min(800, w)
            region_h = min(600, h)
            region_left = left + (w - region_w) // 2
            region_top = top + (h - region_h) // 2
            return {
                'top': region_top,
                'left': region_left,
                'width': region_w,
                'height': region_h,
                'window_offset': (region_left, region_top)
            }
        else:
            # Fallback to primary monitor center
            monitor = self.sct.monitors[1]
            w, h = 800, 600
            left, top = (monitor['width'] - w) // 2, (monitor['height'] - h) // 2
            return {
                'top': top,
                'left': left,
                'width': w,
                'height': h,
                'window_offset': (left, top)
            }
    
    def detect_by_template(self, frame: np.ndarray) -> List[dict]:
        """Detect targets using template matching."""
        detections = []
        if self.template is None:
            return detections
        
        try:
            res = cv2.matchTemplate(frame, self.template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= self.config.template_threshold:
                temp_h, temp_w = self.template.shape[:2]
                center_x = max_loc[0] + temp_w // 2
                center_y = max_loc[1] + temp_h // 2
                
                detections.append({
                    'type': 'template',
                    'x': center_x,
                    'y': center_y,
                    'confidence': float(max_val),
                    'bbox': (max_loc[0], max_loc[1], temp_w, temp_h)
                })
        except Exception as e:
            logger.error(f"Template detection error: {e}")
        
        return detections
    
    def detect_by_color(self, frame: np.ndarray) -> List[dict]:
        """Detect targets using color filtering (Fortnite skin tones)."""
        detections = []
        if not self.config.enable_color_detection:
            return detections
        
        try:
            # Convert to HSV for better color filtering
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # Multiple color ranges for Fortnite players (various skin tones and outfit colors)
            # Range 1: Skin tones
            lower1 = np.array([0, 20, 70])
            upper1 = np.array([20, 255, 255])
            # Range 2: Darker skin tones
            lower2 = np.array([0, 30, 40])
            upper2 = np.array([15, 150, 150])
            # Range 3: Common outfit colors (blues, purples, greens)
            lower3 = np.array([90, 50, 50])
            upper3 = np.array([130, 255, 255])
            # Range 4: Red/Orange outfits
            lower4 = np.array([0, 100, 100])
            upper4 = np.array([10, 255, 255])
            
            # Create masks for each range
            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask3 = cv2.inRange(hsv, lower3, upper3)
            mask4 = cv2.inRange(hsv, lower4, upper4)
            
            # Combine masks
            combined_mask = cv2.bitwise_or(mask1, mask2)
            combined_mask = cv2.bitwise_or(combined_mask, mask3)
            combined_mask = cv2.bitwise_or(combined_mask, mask4)
            
            # Apply morphological operations to clean up
            kernel = np.ones((3, 3), np.uint8)
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
            
            # Find contours in combined mask
            contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area >= self.config.min_body_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    # Filter by aspect ratio (human bodies are typically taller than wide)
                    aspect_ratio = h / w if w > 0 else 0
                    if 1.5 <= aspect_ratio <= 5.0:  # Human-like aspect ratio
                        detections.append({
                            'type': 'color',
                            'x': center_x,
                            'y': center_y,
                            'confidence': min(1.0, area / 10000.0),
                            'bbox': (x, y, w, h)
                        })
        except Exception as e:
            logger.error(f"Color detection error: {e}")
        
        return detections
    
    def detect_by_yolo(self, frame: np.ndarray) -> List[dict]:
        """Detect targets using YOLO AI model."""
        detections = []
        if not self.config.enable_yolo or self.yolo_model is None:
            return detections
        
        try:
            # Run YOLO inference
            results = self.yolo_model(frame, conf=self.config.yolo_confidence, verbose=False)
            
            # Process results
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    # Filter for person class (class 0 in COCO dataset)
                    if class_id == 0:  # Person class
                        center_x = int((x1 + x2) / 2)
                        center_y = int((y1 + y2) / 2)
                        width = int(x2 - x1)
                        height = int(y2 - y1)
                        
                        detections.append({
                            'type': 'yolo',
                            'x': center_x,
                            'y': center_y,
                            'confidence': confidence,
                            'bbox': (int(x1), int(y1), width, height)
                        })
            
            logger.debug(f"YOLO detected {len(detections)} persons")
        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
        
        return detections
    
    def detect_by_contour(self, frame: np.ndarray) -> List[dict]:
        """Detect targets using contour analysis."""
        detections = []
        if not self.config.enable_contour_detection:
            return detections
        
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (9, 9), 0)
            _, thresh = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area >= self.config.min_body_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    detections.append({
                        'type': 'contour',
                        'x': center_x,
                        'y': center_y,
                        'confidence': min(1.0, area / 10000.0),
                        'bbox': (x, y, w, h)
                    })
        except Exception as e:
            logger.error(f"Contour detection error: {e}")
        
        return detections
    
    def detect_by_movement(self, frame: np.ndarray) -> List[dict]:
        """Detect targets using movement tracking."""
        detections = []
        if not self.config.enable_movement_detection or self.previous_frame is None:
            self.previous_frame = frame.copy()
            return detections
        
        try:
            # Calculate frame difference
            gray_prev = cv2.cvtColor(self.previous_frame, cv2.COLOR_BGR2GRAY)
            gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray_prev, gray_curr)
            
            # Threshold difference
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area >= self.config.min_body_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    detections.append({
                        'type': 'movement',
                        'x': center_x,
                        'y': center_y,
                        'confidence': min(1.0, area / 5000.0),
                        'bbox': (x, y, w, h)
                    })
            
            self.previous_frame = frame.copy()
        except Exception as e:
            logger.error(f"Movement detection error: {e}")
        
        return detections
    
    def merge_detections(self, all_detections: List[List[dict]]) -> List[dict]:
        """Merge detections from different methods and remove duplicates."""
        merged = []
        seen_positions = set()
        
        for detections in all_detections:
            for det in detections:
                pos_key = (int(det['x'] // 10), int(det['y'] // 10))  # Quantize position
                if pos_key not in seen_positions:
                    seen_positions.add(pos_key)
                    merged.append(det)
        
        return merged
    
    def select_best_target(self, detections: List[dict], crosshair_x: int, crosshair_y: int) -> Optional[dict]:
        """Select the best target based on priority and distance to crosshair."""
        if not detections:
            return None
        
        # Calculate distance to crosshair for each detection
        for det in detections:
            dx = det['x'] - crosshair_x
            dy = det['y'] - crosshair_y
            det['distance'] = math.sqrt(dx * dx + dy * dy)
        
        # Filter by FOV
        fov_radius = self.config.fov_size
        fov_detections = [d for d in detections if d['distance'] <= fov_radius]
        
        if not fov_detections:
            return None
        
        # Select based on priority
        priority = self.config.target_priority
        
        if priority == TargetPriority.NEAREST.value:
            # Sort by distance (closest to crosshair)
            fov_detections.sort(key=lambda x: x['distance'])
            return fov_detections[0]
        
        elif priority == TargetPriority.HEAD.value:
            # Prefer higher Y positions (head is typically higher)
            fov_detections.sort(key=lambda x: x['y'])
            return fov_detections[0]
        
        elif priority == TargetPriority.CENTER_MASS.value:
            # Prefer center of detections
            fov_detections.sort(key=lambda x: x['confidence'], reverse=True)
            return fov_detections[0]
        
        else:  # UPPER_BODY
            # Prefer upper middle
            fov_detections.sort(key=lambda x: (x['y'], -x['confidence']))
            return fov_detections[0]
    
    def run(self):
        """Main detection loop."""
        self.running = True
        logger.info("Detection engine started")
        
        while self.running:
            if self.paused:
                self.msleep(50)
                continue
            
            start_time = time.time()
            
            try:
                # Capture frame
                scr = np.array(self.sct.grab(self.capture_area))
                frame = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
                
                # Run detection methods
                template_dets = self.detect_by_template(frame)
                color_dets = self.detect_by_color(frame)
                contour_dets = self.detect_by_contour(frame)
                movement_dets = self.detect_by_movement(frame)
                yolo_dets = self.detect_by_yolo(frame)
                
                # Merge detections (YOLO detections have highest priority)
                all_detections = self.merge_detections([yolo_dets, template_dets, color_dets, contour_dets, movement_dets])
                
                # Get crosshair position (center of capture area)
                crosshair_x = self.capture_area['width'] // 2
                crosshair_y = self.capture_area['height'] // 2
                
                # Select best target
                best_target = self.select_best_target(all_detections, crosshair_x, crosshair_y)
                
                # Convert to screen coordinates
                if best_target:
                    offset_x, offset_y = self.capture_area['window_offset']
                    best_target['screen_x'] = int(best_target['x'] + offset_x)
                    best_target['screen_y'] = int(best_target['y'] + offset_y)
                
                # Emit signals
                self.frame_ready.emit(frame, {'detections': all_detections, 'best_target': best_target})
                
                # Only emit target detected if activation key is pressed AND aimbot is enabled
                if best_target and self.activation_key_pressed and self.config.enabled:
                    self.target_detected.emit(best_target)
                
                # Calculate FPS
                self.frame_count += 1
                detection_time = time.time() - start_time
                self.detection_times.append(detection_time)
                if len(self.detection_times) > 60:
                    self.detection_times.pop(0)
                
                if self.frame_count % 30 == 0:
                    avg_time = sum(self.detection_times) / len(self.detection_times)
                    self.fps = 1.0 / avg_time if avg_time > 0 else 0
                    self.performance_stats.emit({
                        'fps': self.fps,
                        'detection_time': avg_time * 1000,
                        'detections_count': len(all_detections)
                    })
                
                # FPS limiting
                target_delay = max(0, (1.0 / self.config.detection_fps_limit) - detection_time)
                self.msleep(int(target_delay * 1000))
                
            except Exception as e:
                logger.error(f"Detection loop error: {e}")
                self.msleep(100)
        
        logger.info("Detection engine stopped")
    
    def stop(self):
        """Stop the detection engine."""
        self.running = False
        self.wait()


# ==================== ACTIVATION KEY LISTENER ====================

class ActivationKeyListener(QThread):
    """Listens for activation key presses (mouse or keyboard)."""
    key_state_changed = pyqtSignal(bool)
    toggle_requested = pyqtSignal()
    
    def __init__(self, activation_key: str, toggle_key: str):
        super().__init__()
        self.activation_key = activation_key
        self.toggle_key = toggle_key
        self.running = False
        self.mouse_listener = None
        self.keyboard_listener = None
    
    def on_mouse_press(self, x, y, button, pressed):
        """Handle mouse button press/release."""
        if self.activation_key == f"mouse_{button.name}":
            self.key_state_changed.emit(pressed)
    
    def on_key_press(self, key):
        """Handle keyboard key press."""
        try:
            # Check for toggle key (P key)
            if hasattr(key, 'char') and key.char == self.toggle_key:
                self.toggle_requested.emit()
                return
            
            # Check for activation key
            if hasattr(key, 'char') and key.char == self.activation_key:
                self.key_state_changed.emit(True)
        except AttributeError:
            # Special keys (shift, ctrl, etc.)
            if key.name.lower() == self.activation_key.lower():
                self.key_state_changed.emit(True)
    
    def on_key_release(self, key):
        """Handle keyboard key release."""
        try:
            if hasattr(key, 'char') and key.char == self.activation_key:
                self.key_state_changed.emit(False)
        except AttributeError:
            # Special keys (shift, ctrl, etc.)
            if key.name.lower() == self.activation_key.lower():
                self.key_state_changed.emit(False)
    
    def run(self):
        """Start the listeners."""
        self.running = True
        
        # Start mouse listener if activation key is mouse button
        if self.activation_key.startswith("mouse_"):
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_press)
            self.mouse_listener.start()
        
        # Start keyboard listener (for both toggle and activation keys)
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )
        self.keyboard_listener.start()
        
        logger.info(f"Key listener started - Toggle: {self.toggle_key}, Activation: {self.activation_key}")
        
        # Keep thread alive
        while self.running:
            self.msleep(100)
    
    def stop(self):
        """Stop the listeners."""
        self.running = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.wait()


# ==================== AIMBOT ENGINE ====================

class AimbotEngine(QThread):
    """
    Aimbot engine with humanized snapping and bezier curves.
    Handles mouse movement with anti-detection considerations.
    """
    aim_complete = pyqtSignal()
    target_position = pyqtSignal(int, int)  # Emits target x, y when aiming
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.running = False
        self.current_target: Optional[dict] = None
        self.target_history: List[dict] = []
        self.last_aim_time = 0
        
        # Velocity estimation for prediction
        self.target_velocity = (0, 0)
    
    def update_target(self, target: dict):
        """Update current target and estimate velocity."""
        if target is None:
            self.current_target = None
            self.target_history = []
            return
        
        # Emit target position for FOV tracking
        self.target_position.emit(target['x'], target['y'])
        
        # Calculate velocity from history
        if len(self.target_history) > 0:
            last_target = self.target_history[-1]
            dt = time.time() - last_target['timestamp']
            if dt > 0:
                vx = (target['x'] - last_target['x']) / dt
                vy = (target['y'] - last_target['y']) / dt
                target['velocity'] = (vx, vy)
        
        target['timestamp'] = time.time()
        self.current_target = target
        self.target_history.append(target)
        self.last_aim_time = time.time()
        
        # Keep only recent history
        if len(self.target_history) > 10:
            self.target_history.pop(0)
    
    def predict_target_position(self, target: dict, prediction_time: float) -> Tuple[int, int]:
        """Predict target position based on velocity."""
        if prediction_time <= 0:
            return target['screen_x'], target['screen_y']
        
        pred_x = target['screen_x'] + self.target_velocity[0] * prediction_time
        pred_y = target['screen_y'] + self.target_velocity[1] * prediction_time
        
        return int(pred_x), int(pred_y)
    
    def humanized_move(self, target_x: int, target_y: int):
        """Move mouse with humanized bezier curve motion."""
        preset = SNAP_PRESETS.get(self.config.snap_preset, SNAP_PRESETS[SnapPreset.MEDIUM.value])
        
        # Get current position
        start_x, start_y = pyautogui.position()
        
        # Calculate distance
        dx = target_x - start_x
        dy = target_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)
        
        # Apply randomization
        target_x = int(apply_randomization(target_x, preset.randomization))
        target_y = int(apply_randomization(target_y, preset.randomization))
        
        # Apply anti-recoil prediction
        pred_x, pred_y = self.predict_target_position(
            {'screen_x': target_x, 'screen_y': target_y},
            preset.duration * 0.5
        )
        
        # Calculate number of steps
        steps = max(5, int(preset.duration * 100))
        step_delay = preset.duration / steps
        
        # Humanized movement with bezier easing
        for i in range(steps + 1):
            t = i / steps
            eased_t = bezier_easing(t, preset.curve_power)
            
            # Apply smoothing and acceleration
            smoothed_t = eased_t * preset.smoothing + t * (1 - preset.smoothing)
            
            # Calculate intermediate position
            curr_x = int(start_x + (pred_x - start_x) * smoothed_t)
            curr_y = int(start_y + (pred_y - start_y) * smoothed_t)
            
            # Add micro-jitter for humanization
            if self.config.humanization_factor > 0:
                jitter = int(self.config.humanization_factor * 2)
                curr_x += random.randint(-jitter, jitter)
                curr_y += random.randint(-jitter, jitter)
            
            pyautogui.moveTo(curr_x, curr_y, duration=0)
            
            # Variable delay for more natural movement
            actual_delay = apply_randomization(step_delay, 0.2)
            time.sleep(max(0, actual_delay))
        
        self.aim_complete.emit()
    
    def run(self):
        """Main aimbot loop."""
        self.running = True
        logger.info("Aimbot engine started")
        
        while self.running:
            try:
                if self.current_target is not None:
                    # Apply random delay before aiming (anti-detection)
                    delay = random.uniform(
                        self.config.random_delay_min,
                        self.config.random_delay_max
                    )
                    time.sleep(delay)
                    
                    # Perform humanized aim
                    self.humanized_move(
                        self.current_target['screen_x'],
                        self.current_target['screen_y']
                    )
                    
                    # Clear target after aiming
                    self.current_target = None
                
                self.msleep(10)
                
            except Exception as e:
                logger.error(f"Aimbot loop error: {e}")
                self.msleep(100)
        
        logger.info("Aimbot engine stopped")
    
    def stop(self):
        """Stop the aimbot engine."""
        self.running = False
        self.wait()


# ==================== FOV OVERLAY WINDOW ====================

class FovOverlayWindow(QtWidgets.QWidget):
    """Transparent always-on-top FOV overlay window that attaches to Fortnite window."""
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WA_TranslucentBackground
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        self.fortnite_hwnd = None
        self.fortnite_rect = get_fortnite_window_rect()
        self.setup_geometry()
        self.attach_to_fortnite()
        
        # Target tracking
        self.target_x = None
        self.target_y = None
        self.is_aiming = False
        
        # Timer to continuously track Fortnite window position
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.track_window_position)
        self.position_timer.start(100)  # Check every 100ms
        
        self.hide()
    
    def set_target_position(self, x: int, y: int):
        """Update target position for FOV tracking."""
        self.target_x = x
        self.target_y = y
        self.is_aiming = True
        self.update()  # Trigger repaint
    
    def clear_target(self):
        """Clear target position and return to center."""
        self.target_x = None
        self.target_y = None
        self.is_aiming = False
        self.update()  # Trigger repaint
    
    def attach_to_fortnite(self):
        """Attach overlay window to Fortnite window using win32gui."""
        try:
            import win32gui
            import win32process
            
            # Find Fortnite window handle
            def enum_callback(hwnd, _):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    for proc in psutil.process_iter(['pid', 'name']):
                        if proc.info['pid'] == pid and proc.info['name'] == "FortniteClient-Win64-Shipping.exe":
                            self.fortnite_hwnd = hwnd
                            return False  # Stop enumeration
                except Exception:
                    pass
                return True
            
            win32gui.EnumWindows(enum_callback, None)
            
            # If found, set this window as a child of Fortnite window
            if self.fortnite_hwnd:
                # Get the window handle of this Qt widget
                self_hwnd = int(self.winId())
                # Set parent to Fortnite window (this makes it follow the window)
                win32gui.SetParent(self_hwnd, self.fortnite_hwnd)
                logger.info(f"FOV overlay attached to Fortnite window (HWND: {self.fortnite_hwnd})")
            else:
                logger.warning("Could not attach to Fortnite window - will use position tracking instead")
                
        except ImportError:
            logger.warning("win32gui not available - using position tracking only")
        except Exception as e:
            logger.error(f"Error attaching to Fortnite window: {e}")
    
    def track_window_position(self):
        """Continuously track Fortnite window position and update overlay."""
        if not self.config.show_fov_overlay:
            return
        
        # Get current Fortnite window position
        current_rect = get_fortnite_window_rect()
        
        if current_rect and current_rect != self.fortnite_rect:
            self.fortnite_rect = current_rect
            self.setup_geometry()
    
    def setup_geometry(self):
        """Setup window geometry based on Fortnite window or primary monitor."""
        if self.fortnite_rect:
            left, top, right, bottom = self.fortnite_rect
            self.setGeometry(left, top, right - left, bottom - top)
        else:
            screen = QtWidgets.QApplication.primaryScreen()
            geometry = screen.geometry()
            self.setGeometry(geometry)
    
    def paintEvent(self, event):
        """Paint the FOV circle overlay."""
        if not self.config.show_fov_overlay:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get center position (target if aiming, otherwise screen center)
        if self.is_aiming and self.target_x is not None and self.target_y is not None:
            center = QPoint(self.target_x, self.target_y)
        else:
            center = self.rect().center()
        
        radius = self.config.fov_size
        
        # Draw FOV circle
        pen = QPen(QColor(0, 255, 0, 100))  # Semi-transparent green
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)
        
        # Draw crosshair
        crosshair_size = 10
        painter.setPen(QPen(QColor(255, 0, 0, 150), 1))
        painter.drawLine(
            center.x() - crosshair_size, center.y(),
            center.x() + crosshair_size, center.y()
        )
        painter.drawLine(
            center.x(), center.y() - crosshair_size,
            center.x(), center.y() + crosshair_size
        )
    
    def update_config(self, config: Config):
        """Update configuration and repaint."""
        self.config = config
        self.setup_geometry()
        if self.config.show_fov_overlay:
            self.show()
        else:
            self.hide()
        self.update()


# ==================== DEBUG WINDOW ====================

class DebugWindow(QtWidgets.QWidget):
    """Debug window showing detected targets and performance stats."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aim Snap Debug")
        self.setGeometry(300, 300, 640, 480)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        
        # Image label
        self.image_label = QtWidgets.QLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setStyleSheet("background-color: black;")
        
        # Stats label
        self.stats_label = QtWidgets.QLabel("FPS: 0 | Detection Time: 0ms | Detections: 0")
        self.stats_label.setStyleSheet("color: white; background-color: rgba(0,0,0,150); padding: 5px;")
        
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.stats_label)
        layout.addWidget(self.image_label)
        self.setLayout(layout)
        
        self.current_frame = None
        self.detections = []
    
    def update_frame(self, frame: np.ndarray, data: dict):
        """Update debug display with new frame and detections."""
        self.current_frame = frame.copy()
        self.detections = data.get('detections', [])
        best_target = data.get('best_target')
        
        # Draw detections
        for det in self.detections:
            x, y, w, h = det['bbox']
            color = (0, 255, 0) if det == best_target else (0, 0, 255)
            cv2.rectangle(self.current_frame, (x, y), (x + w, y + h), color, 2)
        
        # Draw crosshair
        h, w = self.current_frame.shape[:2]
        cv2.line(self.current_frame, (w//2 - 10, h//2), (w//2 + 10, h//2), (255, 0, 0), 2)
        cv2.line(self.current_frame, (w//2, h//2 - 10), (w//2, h//2 + 10), (255, 0, 0), 2)
        
        # Convert to QImage
        rgb_image = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        q_image = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        
        # Scale to fit
        pixmap = QtGui.QPixmap.fromImage(q_image).scaled(
            640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        
        self.image_label.setPixmap(pixmap)
    
    def update_stats(self, stats: dict):
        """Update performance statistics."""
        self.stats_label.setText(
            f"FPS: {stats['fps']:.1f} | "
            f"Detection Time: {stats['detection_time']:.1f}ms | "
            f"Detections: {stats['detections_count']}"
        )


# ==================== MAIN GUI WINDOW ====================

class MainWindow(QtWidgets.QMainWindow):
    """Main GUI window with all controls and settings."""
    
    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.setWindowTitle("Fortnite Master Aim Snap System")
        self.setGeometry(100, 100, 500, 700)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Initialize components
        self.detection_engine = DetectionEngine(self.config)
        self.aimbot_engine = AimbotEngine(self.config)
        self.fov_overlay = FovOverlayWindow(self.config)
        self.debug_window = DebugWindow()
        self.activation_key_listener = ActivationKeyListener(self.config.activation_key, self.config.toggle_key)
        
        # Setup UI
        self.setup_ui()
        
        # Connect signals
        self.connect_signals()
        
        # Start engines
        self.detection_engine.start()
        self.aimbot_engine.start()
        self.activation_key_listener.start()
        
        # Show FOV overlay if enabled
        if self.config.show_fov_overlay:
            self.fov_overlay.show()
        
        # Show debug window if enabled
        if self.config.debug_mode:
            self.debug_window.show()
        
        logger.info("Main window initialized")
    
    def apply_dark_theme(self):
        """Apply modern dark theme QSS styling."""
        qss = """
        QMainWindow {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        
        QWidget {
            background-color: #2d2d2d;
            color: #ffffff;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10pt;
        }
        
        QPushButton {
            background-color: #3d3d3d;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 8px 16px;
            color: white;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #4d4d4d;
            border-color: #0078d4;
        }
        
        QPushButton:pressed {
            background-color: #0078d4;
        }
        
        QPushButton#toggleBtn {
            font-size: 14pt;
            padding: 12px 24px;
            border-radius: 8px;
        }
        
        QPushButton#toggleBtn[enabled="true"] {
            background-color: #00a800;
            border-color: #00ff00;
        }
        
        QPushButton#toggleBtn[enabled="false"] {
            background-color: #a80000;
            border-color: #ff0000;
        }
        
        QLabel {
            color: #ffffff;
            padding: 4px;
        }
        
        QLabel#statusLabel {
            font-size: 18pt;
            font-weight: bold;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }
        
        QLabel#statusLabel[enabled="true"] {
            color: #00ff00;
            background-color: rgba(0, 255, 0, 0.1);
        }
        
        QLabel#statusLabel[enabled="false"] {
            color: #ff0000;
            background-color: rgba(255, 0, 0, 0.1);
        }
        
        QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #3d3d3d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 5px;
            color: white;
        }
        
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
            border-color: #0078d4;
        }
        
        QComboBox::drop-down {
            border: none;
        }
        
        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid white;
            margin-right: 5px;
        }
        
        QSlider::groove:horizontal {
            height: 8px;
            background: #3d3d3d;
            border-radius: 4px;
        }
        
        QSlider::handle:horizontal {
            background: #0078d4;
            border: 2px solid #555;
            width: 18px;
            height: 18px;
            margin: -5px 0;
            border-radius: 9px;
        }
        
        QSlider::handle:horizontal:hover {
            background: #00a8ff;
        }
        
        QGroupBox {
            border: 1px solid #555;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
            font-weight: bold;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        
        QCheckBox {
            spacing: 8px;
        }
        
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border: 2px solid #555;
            border-radius: 3px;
            background-color: #3d3d3d;
        }
        
        QCheckBox::indicator:checked {
            background-color: #0078d4;
            border-color: #0078d4;
        }
        
        QCheckBox::indicator:hover {
            border-color: #0078d4;
        }
        
        QTabWidget::pane {
            border: 1px solid #555;
            background-color: #2d2d2d;
        }
        
        QTabBar::tab {
            background-color: #3d3d3d;
            border: 1px solid #555;
            padding: 8px 16px;
            margin-right: 2px;
        }
        
        QTabBar::tab:selected {
            background-color: #0078d4;
            border-color: #0078d4;
        }
        
        QTabBar::tab:hover:!selected {
            background-color: #4d4d4d;
        }
        """
        self.setStyleSheet(qss)
    
    def setup_ui(self):
        """Setup the main UI layout."""
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        
        # Status section
        status_group = QtWidgets.QGroupBox("Status")
        status_layout = QtWidgets.QVBoxLayout()
        
        self.status_label = QtWidgets.QLabel("AIM SNAP: OFF")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setProperty("enabled", False)
        self.status_label.setAlignment(Qt.AlignCenter)
        
        self.toggle_btn = QtWidgets.QPushButton("ENABLE AIM SNAP")
        self.toggle_btn.setObjectName("toggleBtn")
        self.toggle_btn.setProperty("enabled", False)
        self.toggle_btn.clicked.connect(self.toggle_aim_snap)
        
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.toggle_btn)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # Tab widget for settings
        tab_widget = QtWidgets.QTabWidget()
        
        # General tab
        general_tab = QtWidgets.QWidget()
        general_layout = QtWidgets.QVBoxLayout()
        
        # Aim mode
        general_layout.addWidget(QtWidgets.QLabel("Aim Mode:"))
        self.aim_mode_combo = QtWidgets.QComboBox()
        self.aim_mode_combo.addItems([mode.value for mode in AimMode])
        self.aim_mode_combo.setCurrentText(self.config.aim_mode)
        general_layout.addWidget(self.aim_mode_combo)
        
        # Snap preset
        general_layout.addWidget(QtWidgets.QLabel("Snap Strength Preset:"))
        self.snap_preset_combo = QtWidgets.QComboBox()
        self.snap_preset_combo.addItems([preset.value for preset in SnapPreset])
        self.snap_preset_combo.setCurrentText(self.config.snap_preset)
        self.snap_preset_combo.currentTextChanged.connect(self.on_snap_preset_changed)
        general_layout.addWidget(self.snap_preset_combo)
        
        # Target priority
        general_layout.addWidget(QtWidgets.QLabel("Target Priority:"))
        self.target_priority_combo = QtWidgets.QComboBox()
        self.target_priority_combo.addItems([priority.value for priority in TargetPriority])
        self.target_priority_combo.setCurrentText(self.config.target_priority)
        general_layout.addWidget(self.target_priority_combo)
        
        # Activation key (hold to snap)
        general_layout.addWidget(QtWidgets.QLabel("Activation Key (Hold to Snap):"))
        self.activation_key_combo = QtWidgets.QComboBox()
        self.activation_key_combo.addItems(["mouse_right", "mouse_left", "mouse_middle", "x", "z", "shift"])
        self.activation_key_combo.setCurrentText(self.config.activation_key)
        general_layout.addWidget(self.activation_key_combo)
        
        # Toggle key (toggle on/off)
        general_layout.addWidget(QtWidgets.QLabel("Toggle Key (P to Toggle On/Off):"))
        self.toggle_key_label = QtWidgets.QLabel(f"P")
        self.toggle_key_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        general_layout.addWidget(self.toggle_key_label)
        
        general_layout.addStretch()
        general_tab.setLayout(general_layout)
        tab_widget.addTab(general_tab, "General")
        
        # FOV tab
        fov_tab = QtWidgets.QWidget()
        fov_layout = QtWidgets.QVBoxLayout()
        
        # FOV size
        fov_layout.addWidget(QtWidgets.QLabel("FOV Size:"))
        self.fov_size_spin = QtWidgets.QSpinBox()
        self.fov_size_spin.setRange(50, 500)
        self.fov_size_spin.setValue(self.config.fov_size)
        self.fov_size_spin.valueChanged.connect(self.on_fov_size_changed)
        fov_layout.addWidget(self.fov_size_spin)
        
        # Show FOV overlay
        self.show_fov_overlay_check = QtWidgets.QCheckBox("Show FOV Overlay")
        self.show_fov_overlay_check.setChecked(self.config.show_fov_overlay)
        self.show_fov_overlay_check.toggled.connect(self.on_fov_overlay_toggled)
        fov_layout.addWidget(self.show_fov_overlay_check)
        
        fov_layout.addStretch()
        fov_tab.setLayout(fov_layout)
        tab_widget.addTab(fov_tab, "FOV")
        
        # Detection tab
        detection_tab = QtWidgets.QWidget()
        detection_layout = QtWidgets.QVBoxLayout()
        
        # Template threshold
        detection_layout.addWidget(QtWidgets.QLabel("Template Threshold:"))
        self.template_threshold_spin = QtWidgets.QDoubleSpinBox()
        self.template_threshold_spin.setRange(0.0, 1.0)
        self.template_threshold_spin.setSingleStep(0.01)
        self.template_threshold_spin.setValue(self.config.template_threshold)
        detection_layout.addWidget(self.template_threshold_spin)
        
        # Detection method toggles
        self.enable_color_check = QtWidgets.QCheckBox("Enable Color Detection")
        self.enable_color_check.setChecked(self.config.enable_color_detection)
        detection_layout.addWidget(self.enable_color_check)
        
        self.enable_contour_check = QtWidgets.QCheckBox("Enable Contour Detection")
        self.enable_contour_check.setChecked(self.config.enable_contour_detection)
        detection_layout.addWidget(self.enable_contour_check)
        
        self.enable_movement_check = QtWidgets.QCheckBox("Enable Movement Detection")
        self.enable_movement_check.setChecked(self.config.enable_movement_detection)
        detection_layout.addWidget(self.enable_movement_check)
        
        self.enable_yolo_check = QtWidgets.QCheckBox("Enable YOLO AI Detection")
        self.enable_yolo_check.setChecked(self.config.enable_yolo)
        self.enable_yolo_check.setEnabled(AI_AVAILABLE)  # Enable if AI dependencies available
        detection_layout.addWidget(self.enable_yolo_check)
        
        # YOLO model selection
        detection_layout.addWidget(QtWidgets.QLabel("YOLO Model:"))
        self.yolo_model_combo = QtWidgets.QComboBox()
        self.yolo_model_combo.addItems(["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"])
        self.yolo_model_combo.setCurrentText(self.config.yolo_model)
        self.yolo_model_combo.setEnabled(AI_AVAILABLE)
        detection_layout.addWidget(self.yolo_model_combo)
        
        # YOLO confidence threshold
        detection_layout.addWidget(QtWidgets.QLabel("YOLO Confidence:"))
        self.yolo_confidence_spin = QtWidgets.QDoubleSpinBox()
        self.yolo_confidence_spin.setRange(0.1, 1.0)
        self.yolo_confidence_spin.setSingleStep(0.05)
        self.yolo_confidence_spin.setValue(self.config.yolo_confidence)
        self.yolo_confidence_spin.setEnabled(AI_AVAILABLE)
        detection_layout.addWidget(self.yolo_confidence_spin)
        
        # YOLO GPU toggle
        self.yolo_gpu_check = QtWidgets.QCheckBox("Use GPU Acceleration")
        self.yolo_gpu_check.setChecked(self.config.yolo_use_gpu)
        self.yolo_gpu_check.setEnabled(AI_AVAILABLE and torch.cuda.is_available() if AI_AVAILABLE else False)
        detection_layout.addWidget(self.yolo_gpu_check)
        
        # AI status label
        self.ai_status_label = QtWidgets.QLabel("AI Status: " + ("Available (GPU)" if AI_AVAILABLE and torch.cuda.is_available() else "Not Available"))
        self.ai_status_label.setStyleSheet("color: #00ff00;" if AI_AVAILABLE else "color: #ff0000;")
        detection_layout.addWidget(self.ai_status_label)
        
        # Min body area
        detection_layout.addWidget(QtWidgets.QLabel("Min Body Area:"))
        self.min_body_area_spin = QtWidgets.QSpinBox()
        self.min_body_area_spin.setRange(50, 2000)
        self.min_body_area_spin.setValue(self.config.min_body_area)
        detection_layout.addWidget(self.min_body_area_spin)
        
        detection_layout.addStretch()
        detection_tab.setLayout(detection_layout)
        tab_widget.addTab(detection_tab, "Detection")
        
        # Anti-Detection tab
        anti_detection_tab = QtWidgets.QWidget()
        anti_detection_layout = QtWidgets.QVBoxLayout()
        
        # Random delay
        anti_detection_layout.addWidget(QtWidgets.QLabel("Random Delay Min (s):"))
        self.random_delay_min_spin = QtWidgets.QDoubleSpinBox()
        self.random_delay_min_spin.setRange(0.0, 0.5)
        self.random_delay_min_spin.setSingleStep(0.01)
        self.random_delay_min_spin.setValue(self.config.random_delay_min)
        anti_detection_layout.addWidget(self.random_delay_min_spin)
        
        anti_detection_layout.addWidget(QtWidgets.QLabel("Random Delay Max (s):"))
        self.random_delay_max_spin = QtWidgets.QDoubleSpinBox()
        self.random_delay_max_spin.setRange(0.0, 0.5)
        self.random_delay_max_spin.setSingleStep(0.01)
        self.random_delay_max_spin.setValue(self.config.random_delay_max)
        anti_detection_layout.addWidget(self.random_delay_max_spin)
        
        # Humanization factor
        anti_detection_layout.addWidget(QtWidgets.QLabel("Humanization Factor:"))
        self.humanization_factor_spin = QtWidgets.QDoubleSpinBox()
        self.humanization_factor_spin.setRange(0.0, 1.0)
        self.humanization_factor_spin.setSingleStep(0.1)
        self.humanization_factor_spin.setValue(self.config.humanization_factor)
        anti_detection_layout.addWidget(self.humanization_factor_spin)
        
        anti_detection_layout.addStretch()
        anti_detection_tab.setLayout(anti_detection_layout)
        tab_widget.addTab(anti_detection_tab, "Anti-Detection")
        
        # Performance tab
        performance_tab = QtWidgets.QWidget()
        performance_layout = QtWidgets.QVBoxLayout()
        
        # FPS limit
        performance_layout.addWidget(QtWidgets.QLabel("Detection FPS Limit:"))
        self.fps_limit_spin = QtWidgets.QSpinBox()
        self.fps_limit_spin.setRange(10, 120)
        self.fps_limit_spin.setValue(self.config.detection_fps_limit)
        performance_layout.addWidget(self.fps_limit_spin)
        
        # Debug mode
        self.debug_mode_check = QtWidgets.QCheckBox("Debug Mode (Show Debug Window)")
        self.debug_mode_check.setChecked(self.config.debug_mode)
        self.debug_mode_check.toggled.connect(self.on_debug_mode_toggled)
        performance_layout.addWidget(self.debug_mode_check)
        
        # Minimize to tray
        self.minimize_to_tray_check = QtWidgets.QCheckBox("Minimize to Tray")
        self.minimize_to_tray_check.setChecked(self.config.minimize_to_tray)
        performance_layout.addWidget(self.minimize_to_tray_check)
        
        # Performance stats
        self.perf_stats_label = QtWidgets.QLabel("FPS: 0 | Detection Time: 0ms")
        self.perf_stats_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        performance_layout.addWidget(self.perf_stats_label)
        
        performance_layout.addStretch()
        performance_tab.setLayout(performance_layout)
        tab_widget.addTab(performance_tab, "Performance")
        
        main_layout.addWidget(tab_widget)
        
        # Save/Load buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.save_btn = QtWidgets.QPushButton("Save Settings")
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        self.load_btn = QtWidgets.QPushButton("Load Settings")
        self.load_btn.clicked.connect(self.load_settings)
        button_layout.addWidget(self.load_btn)
        
        main_layout.addLayout(button_layout)
    
    def connect_signals(self):
        """Connect signals from engines to GUI."""
        self.detection_engine.frame_ready.connect(self.on_frame_ready)
        self.detection_engine.target_detected.connect(self.on_target_detected)
        self.detection_engine.performance_stats.connect(self.on_performance_stats)
        self.aimbot_engine.aim_complete.connect(self.on_aim_complete)
        self.aimbot_engine.target_position.connect(self.on_target_position)
        self.activation_key_listener.key_state_changed.connect(self.on_activation_key_changed)
        self.activation_key_listener.toggle_requested.connect(self.toggle_aim_snap)
    
    def toggle_aim_snap(self):
        """Toggle aim snap on/off."""
        self.config.enabled = not self.config.enabled
        
        if self.config.enabled:
            self.status_label.setText("AIM SNAP: ON")
            self.status_label.setProperty("enabled", True)
            self.toggle_btn.setText("DISABLE AIM SNAP")
            self.toggle_btn.setProperty("enabled", True)
            self.detection_engine.paused = False
        else:
            self.status_label.setText("AIM SNAP: OFF")
            self.status_label.setProperty("enabled", False)
            self.toggle_btn.setText("ENABLE AIM SNAP")
            self.toggle_btn.setProperty("enabled", False)
            self.detection_engine.paused = True
        
        # Repaint to apply style changes
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)
    
    def on_snap_preset_changed(self, preset: str):
        """Handle snap preset change."""
        self.config.snap_preset = preset
        logger.info(f"Snap preset changed to: {preset}")
    
    def on_fov_size_changed(self, size: int):
        """Handle FOV size change."""
        self.config.fov_size = size
        self.fov_overlay.update_config(self.config)
    
    def on_fov_overlay_toggled(self, checked: bool):
        """Handle FOV overlay toggle."""
        self.config.show_fov_overlay = checked
        self.fov_overlay.update_config(self.config)
    
    def on_debug_mode_toggled(self, checked: bool):
        """Handle debug mode toggle."""
        self.config.debug_mode = checked
        if checked:
            self.debug_window.show()
        else:
            self.debug_window.hide()
    
    def on_frame_ready(self, frame: np.ndarray, data: dict):
        """Handle new frame from detection engine."""
        if self.config.debug_mode:
            self.debug_window.update_frame(frame, data)
    
    def on_target_detected(self, target: dict):
        """Handle target detection."""
        if self.config.enabled:
            self.aimbot_engine.update_target(target)
    
    def on_performance_stats(self, stats: dict):
        """Handle performance statistics update."""
        self.perf_stats_label.setText(
            f"FPS: {stats['fps']:.1f} | Detection Time: {stats['detection_time']:.1f}ms"
        )
        if self.config.debug_mode:
            self.debug_window.update_stats(stats)
    
    def on_aim_complete(self):
        """Handle aim completion."""
        pass  # Can add visual feedback here
    
    def on_activation_key_changed(self, pressed: bool):
        """Handle activation key state change."""
        self.detection_engine.set_activation_key_state(pressed)
        if not pressed:
            # Clear FOV target when activation key is released
            self.fov_overlay.clear_target()
        logger.debug(f"Activation key state: {pressed}")
    
    def on_target_position(self, x: int, y: int):
        """Handle target position update for FOV tracking."""
        self.fov_overlay.set_target_position(x, y)
    
    def save_settings(self):
        """Save current settings to config file."""
        # Update config from UI
        self.config.aim_mode = self.aim_mode_combo.currentText()
        self.config.snap_preset = self.snap_preset_combo.currentText()
        self.config.target_priority = self.target_priority_combo.currentText()
        self.config.activation_key = self.activation_key_combo.currentText()
        self.config.toggle_key = self.config.toggle_key  # Currently fixed to 'p'
        self.config.fov_size = self.fov_size_spin.value()
        self.config.show_fov_overlay = self.show_fov_overlay_check.isChecked()
        self.config.template_threshold = self.template_threshold_spin.value()
        self.config.enable_color_detection = self.enable_color_check.isChecked()
        self.config.enable_contour_detection = self.enable_contour_check.isChecked()
        self.config.enable_movement_detection = self.enable_movement_check.isChecked()
        self.config.enable_yolo = self.enable_yolo_check.isChecked()
        self.config.yolo_model = self.yolo_model_combo.currentText()
        self.config.yolo_confidence = self.yolo_confidence_spin.value()
        self.config.yolo_use_gpu = self.yolo_gpu_check.isChecked()
        self.config.min_body_area = self.min_body_area_spin.value()
        self.config.random_delay_min = self.random_delay_min_spin.value()
        self.config.random_delay_max = self.random_delay_max_spin.value()
        self.config.humanization_factor = self.humanization_factor_spin.value()
        self.config.detection_fps_limit = self.fps_limit_spin.value()
        self.config.debug_mode = self.debug_mode_check.isChecked()
        self.config.minimize_to_tray = self.minimize_to_tray_check.isChecked()
        
        # Save to file
        if self.config.save():
            QtWidgets.QMessageBox.information(self, "Success", "Settings saved successfully!")
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to save settings.")
    
    def load_settings(self):
        """Load settings from config file."""
        new_config = Config.load()
        if new_config:
            self.config = new_config
            # Update UI from config
            self.aim_mode_combo.setCurrentText(self.config.aim_mode)
            self.snap_preset_combo.setCurrentText(self.config.snap_preset)
            self.target_priority_combo.setCurrentText(self.config.target_priority)
            self.activation_key_combo.setCurrentText(self.config.activation_key)
            self.toggle_key_label.setText(self.config.toggle_key.upper())
            self.fov_size_spin.setValue(self.config.fov_size)
            self.show_fov_overlay_check.setChecked(self.config.show_fov_overlay)
            self.template_threshold_spin.setValue(self.config.template_threshold)
            self.enable_color_check.setChecked(self.config.enable_color_detection)
            self.enable_contour_check.setChecked(self.config.enable_contour_detection)
            self.enable_movement_check.setChecked(self.config.enable_movement_detection)
            self.enable_yolo_check.setChecked(self.config.enable_yolo)
            self.yolo_model_combo.setCurrentText(self.config.yolo_model)
            self.yolo_confidence_spin.setValue(self.config.yolo_confidence)
            self.yolo_gpu_check.setChecked(self.config.yolo_use_gpu)
            self.min_body_area_spin.setValue(self.config.min_body_area)
            self.random_delay_min_spin.setValue(self.config.random_delay_min)
            self.random_delay_max_spin.setValue(self.config.random_delay_max)
            self.humanization_factor_spin.setValue(self.config.humanization_factor)
            self.fps_limit_spin.setValue(self.config.detection_fps_limit)
            self.debug_mode_check.setChecked(self.config.debug_mode)
            self.minimize_to_tray_check.setChecked(self.config.minimize_to_tray)
            
            # Update engines
            self.detection_engine.config = self.config
            self.aimbot_engine.config = self.config
            self.fov_overlay.update_config(self.config)
            
            # Reload YOLO model if settings changed
            if self.config.enable_yolo and AI_AVAILABLE:
                self.detection_engine.load_yolo_model()
            
            QtWidgets.QMessageBox.information(self, "Success", "Settings loaded successfully!")
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to load settings.")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop engines
        self.detection_engine.stop()
        self.aimbot_engine.stop()
        self.activation_key_listener.stop()
        
        # Auto-save settings
        self.save_settings()
        
        # Close windows
        self.fov_overlay.close()
        self.debug_window.close()
        
        event.accept()


# ==================== MAIN ENTRY POINT ====================

def main():
    """Main entry point."""
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Fortnite Master Aim Snap System")
    
    # Check for required dependencies
    try:
        import win32gui
        import win32process
    except ImportError:
        logger.warning("win32gui/win32process not installed. Window detection may not work.")
        logger.warning("Install with: pip install pywin32")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    logger.info("Application started")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
