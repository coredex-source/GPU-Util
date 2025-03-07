# AMD GPU Fan Controller

A Python utility to control fan speeds on AMD Radeon GPUs on Windows.
    - I made this just cause my Mac Pro had an overheating issue and I required a proper solution.

## Requirements

- Windows 10
- AMD Radeon GPU (tested on Radeon 5700)
- AMD Radeon drivers installed
- Python: Minimum 3.6 (untested) || Recommended 3.13 (tested on 3.13.2)
- Packages: pystray, pillow (automatically installed if missing)

## Installation

The script will automatically install required packages (pystray, pillow) if they're not found.

## Usage

### System Tray Monitoring

Simply run the script without arguments to show GPU temperature and fan speed in the system tray:

```
python gpu_fan_controller.py
```

This will:
- Display current temperature and fan speed in the system tray icon
- Update readings approximately every 2 seconds
- Provide a right-click menu with various fan control options

### Setting Fan Speed

Set a specific fan speed (0-100%):

```
python gpu_fan_controller.py 75
```

This sets the fan speed to 75%.

### Using Fan Curves

Apply a saved fan curve:

```
python gpu_fan_controller.py curve
```

Fan curves can be configured through the system tray interface.

### Maintaining Target Temperature

Maintain a specific GPU temperature (default 70°C):

```
python gpu_fan_controller.py temp
```

Or specify a custom temperature:

```
python gpu_fan_controller.py temp 65
```

The temperature control algorithm is adaptive:
- It starts in aggressive mode to quickly reach the target temperature
- Once temperature is stable, it switches to a gentler mode to minimize fan noise
- If temperature becomes unstable again, it automatically switches back to aggressive mode

### Disabling Manual Control

Return to automatic fan control (let the GPU manage fan speeds):

```
python gpu_fan_controller.py disable
```

You can also use `auto` or `default` instead of `disable`.

## System Tray Features

When running in system tray mode:
- The icon displays temperature in the top line and fan speed in the bottom line
- The icon color changes based on temperature (green=cool, orange=warm, red=hot)
- Right-click the icon to access the menu with various control options
- Hover over the icon to see exact temperature, fan speed, and active control mode

### Fan Curve Setup

From the system tray menu, you can:
1. Select "Configure Fan Curve" to open the Fan Curve Setup dialog
2. Enter a name for your curve
3. Define up to 5 temperature/fan speed points using the sliders
4. Click OK to save your curve and choose whether to enable it

The fan curve dialog provides an intuitive interface for setting temperature/fan speed pairs.

### Temperature Target Setup

From the system tray menu, you can:
1. Select "Configure Temp Target" to open the Temperature Control Setup dialog
2. Adjust your desired target temperature using the slider
3. Set minimum and maximum fan speeds
4. Click OK to save your settings and choose whether to enable temperature control

## Saved Settings

Fan curves are saved to the `config` folder and automatically loaded when you restart the application.

## Safety Recommendations

- Be careful when setting very low fan speeds as it may lead to overheating
- Monitor your GPU temperature using the system tray icon
- A minimum fan speed of 30-40% is recommended for most systems under load
- Use the `Auto Control` option in the system tray menu to return to automatic control when you're done

## Notes

- This script requires administrator privileges to control fan settings
- Running at your own risk - improper fan settings could potentially damage your hardware

## Troubleshooting

If you encounter issues:
- Make sure you have the latest AMD drivers installed
- Run the script with administrator privileges (right-click → Run as administrator)
- Verify that your GPU is an AMD Radeon model
- Try using the `disable` command to reset to default settings
- If the system tray icon doesn't appear, check that pystray and pillow are installed

### GUI Freezing Issues

If the application freezes when opening configuration dialogs:
1. Make sure you're using the latest version of the script
2. Try waiting a few seconds - sometimes dialog boxes appear behind other windows
3. Check that no antivirus or security software is blocking the program
4. On Windows, ensure you have the correct permissions to create GUI windows
5. Try running the application with administrator privileges
