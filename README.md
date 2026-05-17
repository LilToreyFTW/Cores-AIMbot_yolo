# Fortnite Master GUI Aim Snap System

A professional, highly configurable, and feature-rich aim assistance tool for Fortnite with modern PyQt5 GUI, hybrid detection system (including YOLOv8 AI detection), and humanized snapping.

## Features

### Core Functionality
- **Modern PyQt5 GUI** with dark theme QSS styling
- **Toggle ON/OFF** with big visible status indicator
- **Snap Strength Presets**: Weak, Medium, Strong, Instant (with smooth humanized curves)
- **FOV Circle** size slider + visual overlay option (transparent always-on-top window)
- **Smoothing/Acceleration** control per preset
- **Target Priority**: Head / Upper Body / Center Mass / Nearest
- **Hotkey support** (Right Mouse Button hold to activate, or custom bind)
- **Auto-detect Fortnite window** + fallback to primary monitor
- **Save/Load settings** (JSON config)

### Detection System (Hybrid)
- **YOLOv8 AI Detection** with GPU acceleration (RTX 5070 optimized)
  - Supports multiple models: yolov8n.pt (nano), yolov8s.pt (small), yolov8m.pt (medium), yolov8l.pt (large)
  - Auto-detects and uses CUDA GPU acceleration when available
  - Highest priority detection method for maximum accuracy
- **Template matching** as fallback
- **Color detection** (Fortnite skin tone filtering)
- **Contour detection** for body shapes
- **Movement detection** for moving objects (optimized)
- **Multi-threaded screen capture** with MSS
- **Proper region limiting** around center of Fortnite window

### Aim Snap Logic
- **Smart target selection** (closest to crosshair + highest confidence)
- **Humanized snapping** using selected preset with bezier-like easing curves
- **Configurable snap duration** per preset
- **Only snap when target** is inside FOV
- **Anti-recoil style prediction** for moving targets (simple velocity estimation)
- **Trigger bot / Aim Assist** mode toggle

### Code Quality
- **Full type hints** throughout
- **Proper threading** (QThread preferred)
- **Clean class separation**: Config, DetectionEngine, AimbotEngine, GUI, Overlay
- **Comprehensive error handling** and logging
- **Anti-detection considerations**: randomization, humanization, delays
- **Well-commented code**

### Extras
- **Enemy color filter** (common Fortnite skin tones)
- **Debug window** showing detected targets
- **Performance stats** (FPS, detection time)
- **Minimize to tray** option

## Installation

1. Install Python 3.8 or higher
2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. For AI Detection (YOLOv8) with GPU acceleration (recommended for RTX 5070):
   - Install PyTorch with CUDA support:
   ```bash
   pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118
   ```
   - The YOLO model will auto-download on first run

4. Ensure you have `target.png` in the same directory (your aim target template)

## Usage

Run the application:
```bash
python aim_snap_master.py
```

### GUI Controls

**Status Section**
- Big toggle button to enable/disable aim snap
- Visual status indicator (green = ON, red = OFF)

**General Tab**
- Aim Mode: Aim Assist / Trigger Bot
- Snap Strength Preset: Weak / Medium / Strong / Instant
- Target Priority: Head / Upper Body / Center Mass / Nearest
- Activation Key: mouse_right / mouse_left / mouse_middle / x / z / shift

**FOV Tab**
- FOV Size slider (50-500 pixels)
- Show FOV Overlay checkbox

**Detection Tab**
- Template Threshold (0.0-1.0)
- Enable Color Detection
- Enable Contour Detection
- Enable Movement Detection
- Enable YOLO (Experimental - disabled by default)
- Min Body Area

**Anti-Detection Tab**
- Random Delay Min/Max (seconds)
- Humanization Factor (0.0-1.0)

**Performance Tab**
- Detection FPS Limit
- Debug Mode (Show Debug Window)
- Minimize to Tray
- Live performance stats

### Settings

Settings are automatically saved to `aim_snap_config.json` when you close the application. You can also manually save/load settings using the buttons at the bottom.

## Configuration

### Snap Presets

Each preset has configurable parameters:
- **Weak**: Slow, smooth movement (duration: 0.25s, smoothing: 0.8)
- **Medium**: Balanced (duration: 0.15s, smoothing: 0.5)
- **Strong**: Fast snap (duration: 0.08s, smoothing: 0.3)
- **Instant**: Near-instant (duration: 0.02s, smoothing: 0.1)

### Detection Methods

The system uses a hybrid approach:
1. **Template Matching**: Matches your target.png template
2. **Color Detection**: Filters by Fortnite skin tones (RGB range)
3. **Contour Detection**: Finds body-shaped contours
4. **Movement Detection**: Tracks moving objects

### Anti-Detection

Built-in anti-detection features:
- Random delays before aiming
- Humanized bezier curve movement
- Micro-jitter for natural feel
- Velocity prediction for moving targets
- Configurable humanization factor

## Troubleshooting

### Fortnite Window Not Found
- Ensure Fortnite is running before starting the tool
- The tool will fallback to primary monitor center if window not found
- Install pywin32: `pip install pywin32`

### Template Not Loading
- Ensure `target.png` exists in the same directory
- The file should be a valid image (PNG format)
- Check the log file `aim_snap.log` for errors

### Poor Detection
- Adjust the Template Threshold (try 0.65-0.80)
- Enable/disable different detection methods
- Adjust Min Body Area based on your resolution
- Update color filter ranges for your region/skins

### Performance Issues
- Reduce Detection FPS Limit
- Disable debug window
- Disable FOV overlay
- Reduce capture area in code

## Architecture

The code is organized into clean, separate classes:

- **Config**: Configuration management with JSON save/load
- **DetectionEngine**: Multi-threaded detection with hybrid methods
- **AimbotEngine**: Humanized aim snapping with bezier curves
- **FovOverlayWindow**: Transparent FOV overlay
- **DebugWindow**: Debug visualization and performance stats
- **MainWindow**: Main GUI with all controls

## Logging

The application logs to `aim_snap.log` with detailed information about:
- Configuration changes
- Detection events
- Performance metrics
- Errors and warnings

## Safety & Disclaimer

This tool is for educational purposes only. Use at your own risk. The developers are not responsible for any consequences of using this software.

## License

This project is provided as-is for educational purposes.

## Requirements

- Python 3.8+
- Windows OS (uses win32gui for window detection)
- PyQt5
- OpenCV
- NumPy
- MSS
- PyAutoGUI
- psutil
- pywin32

## Notes

- The YOLO/ONNX model support is disabled by default and requires additional setup
- Color filter ranges may need adjustment for different Fortnite regions/skins
- For best results, use a high-quality target.png template
- Anti-detection features help but don't guarantee safety
