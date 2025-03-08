#!/usr/bin/env python3
"""
Apple LCD Display Brightness Controller
A system tray utility to control Apple LCD display brightness from 0-250%
"""

import ctypes
import sys
import time
import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from ctypes import windll, byref, Structure, c_ulong, c_void_p, c_byte, c_int

# Try to import required modules
try:
    import wmi
    import pythoncom
    import pystray
    from PIL import Image, ImageDraw
    from win32com.shell import shell, shellcon
    WMI_AVAILABLE = True
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install required packages: pip install wmi pystray pillow pywin32")
    WMI_AVAILABLE = True  # Keep it True to avoid confusing error messages

# Define Windows API structures and constants for display control
class PHYSICAL_MONITOR(Structure):
    _fields_ = [
        ('handle', c_void_p),
        ('description', c_ulong * 128)
    ]

# Constants for display detection and control
MONITOR_DEFAULTTOPRIMARY = 0x00000001
WM_MONITORMAGIC = 0x2111
MC_GETMONITORNAME = 0x0001

# Check if running as admin
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# Re-launch as admin if needed
def run_as_admin():
    script = sys.argv[0]
    if getattr(sys, 'frozen', False):
        args = [sys.executable] + sys.argv[1:]
    else:
        args = [sys.executable, script] + sys.argv[1:]
    
    print("Requesting administrative privileges...")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", args[0], " ".join(args[1:]), None, 1)

# Method 1: Set brightness using WMI
def set_brightness_wmi(brightness=250):
    """Set display brightness using WMI"""
    try:
        if not WMI_AVAILABLE:
            return False
            
        # Initialize COM
        pythoncom.CoInitialize()
        
        # Connect to WMI
        wmi_instance = wmi.WMI(namespace='wmi')
        
        # Find monitors that support brightness control
        monitors = wmi_instance.WmiMonitorBrightnessMethods()
        
        # Check for Apple displays
        apple_found = False
        for monitor in monitors:
            try:
                # Get monitor information
                monitor_info = wmi_instance.WmiMonitorID()[0]
                manufacturer = ''.join([chr(i) for i in monitor_info.ManufacturerName if i > 0])
                
                # Set brightness for all displays, but note if we found Apple
                if 'APPLE' in manufacturer.upper():
                    print(f"Found Apple display: {manufacturer}")
                    apple_found = True
                    
                monitor.WmiSetBrightness(0, brightness)
                print(f"Set brightness to {brightness}% using WMI")
                
            except Exception as e:
                print(f"Error getting monitor info: {e}")
        
        # Uninitialize COM
        pythoncom.CoUninitialize()
        
        return apple_found
        
    except Exception as e:
        print(f"WMI error: {e}")
        return False

# Method 2: Set brightness using DDC/CI
def set_brightness_ddc(brightness=250):
    """Set display brightness using DDC/CI commands"""
    try:
        # Get primary monitor
        hMonitor = windll.user32.MonitorFromWindow(
            windll.user32.GetDesktopWindow(),
            MONITOR_DEFAULTTOPRIMARY
        )
        
        if not hMonitor:
            return False
            
        # Get physical monitor counts
        physical_monitor_count = c_ulong()
        if not windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
            hMonitor, byref(physical_monitor_count)):
            return False
            
        # Get physical monitor handles
        physical_monitors = (PHYSICAL_MONITOR * physical_monitor_count.value)()
        if not windll.dxva2.GetPhysicalMonitorsFromHMONITOR(
            hMonitor, physical_monitor_count.value, physical_monitors):
            return False
            
        success = False
        
        # Try to set brightness for each monitor
        for i, monitor in enumerate(physical_monitors):
            # Brightness VCP code is 0x10
            if windll.dxva2.SetVCPFeature(monitor.handle, 0x10, brightness):
                print(f"Set brightness to {brightness}% using DDC/CI on monitor {i+1}")
                success = True
                
        # Cleanup
        windll.dxva2.DestroyPhysicalMonitors(physical_monitor_count.value, physical_monitors)
        
        return success
        
    except Exception as e:
        print(f"DDC/CI error: {e}")
        return False

# Method 3: Set brightness using direct API
def set_brightness_api(brightness=250):
    """Set brightness using direct Windows API calls"""
    try:
        # Get primary monitor
        hMonitor = windll.user32.MonitorFromWindow(
            windll.user32.GetDesktopWindow(),
            MONITOR_DEFAULTTOPRIMARY
        )
        
        if not hMonitor:
            return False
            
        # Get physical monitor counts
        physical_monitor_count = c_ulong()
        if not windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
            hMonitor, byref(physical_monitor_count)):
            return False
            
        # Get physical monitor handles
        physical_monitors = (PHYSICAL_MONITOR * physical_monitor_count.value)()
        if not windll.dxva2.GetPhysicalMonitorsFromHMONITOR(
            hMonitor, physical_monitor_count.value, physical_monitors):
            return False
            
        success = False
        
        # Try to set brightness for each monitor
        for i, monitor in enumerate(physical_monitors):
            if windll.dxva2.SetMonitorBrightness(monitor.handle, brightness):
                print(f"Set brightness to {brightness}% using direct API on monitor {i+1}")
                success = True
                
        # Cleanup
        windll.dxva2.DestroyPhysicalMonitors(physical_monitor_count.value, physical_monitors)
        
        return success
        
    except Exception as e:
        print(f"API error: {e}")
        return False

class BrightnessController:
    def __init__(self):
        self.settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                        "apple_brightness_settings.json")
        self.current_brightness = 250  # Default to max brightness
        self.autostart_enabled = False  # Initialize this flag
        self.load_settings()
        
        # Initialize the system tray
        self.icon = None
        
        # Create but don't show GUI yet
        self.setup_gui()
        
        # Set up the system tray after the GUI
        self.setup_tray()
        
        # Set initial brightness
        self.set_brightness(self.current_brightness)

        # Flag to track exit process
        self.exiting = False
        
    def setup_gui(self):
        """Create the brightness control window"""
        self.root = tk.Tk()
        self.root.title("Apple Display Brightness")
        self.root.geometry("400x140")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # Apply modern style
        style = ttk.Style()
        style.theme_use('clam')  # Use a modern theme
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title label
        title_label = ttk.Label(main_frame, text="Apple Display Brightness Control", 
                               font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Slider frame
        slider_frame = ttk.Frame(main_frame)
        slider_frame.pack(fill=tk.X, pady=5)
        
        # Brightness label
        brightness_label = ttk.Label(slider_frame, text="Brightness:")
        brightness_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Brightness value label
        self.brightness_value_label = ttk.Label(slider_frame, text=f"{self.current_brightness}%", width=5)
        self.brightness_value_label.pack(side=tk.RIGHT)
        
        # Brightness slider
        self.brightness_slider = ttk.Scale(
            main_frame, 
            from_=0, 
            to=250, 
            orient=tk.HORIZONTAL,
            value=self.current_brightness,
            command=self.update_brightness_value
        )
        self.brightness_slider.pack(fill=tk.X)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Apply button
        apply_button = ttk.Button(button_frame, text="Apply", 
                                 command=lambda: self.set_brightness(int(self.brightness_slider.get())))
        apply_button.pack(side=tk.RIGHT)
        
        # Save button
        save_button = ttk.Button(button_frame, text="Save as Default", 
                               command=self.save_settings)
        save_button.pack(side=tk.LEFT)
        
        # Initially hide the window
        self.hide_window()
        
    def update_brightness_value(self, value):
        """Update the brightness value label as slider moves"""
        brightness = int(float(value))
        self.brightness_value_label.config(text=f"{brightness}%")
        
    def set_brightness(self, brightness):
        """Try all methods to set brightness"""
        self.current_brightness = brightness
        
        # Define methods to try
        methods = [
            set_brightness_wmi,
            set_brightness_ddc,
            set_brightness_api
        ]
        
        # Try each method in sequence
        for method in methods:
            try:
                if method(brightness):
                    return True
            except Exception as e:
                print(f"Method failed: {e}")
                
        return False
        
    def setup_tray(self):
        """Create the system tray icon and menu"""
        try:
            # Create an icon
            icon_image = self.create_tray_icon()
            
            # Check if autostart is enabled before setting up menu
            self.autostart_enabled = self.check_autostart_enabled()
            
            # Define menu items correctly - use lambda for checked property
            menu_items = [
                pystray.MenuItem('Brightness Control', self.show_window),
                pystray.MenuItem('Apply 100%', lambda: self.set_brightness(100)),
                pystray.MenuItem('Apply 175%', lambda: self.set_brightness(175)),
                pystray.MenuItem('Apply 250%', lambda: self.set_brightness(250)),
                pystray.MenuItem('Start with Windows', 
                                self.toggle_autostart, 
                                lambda item: self.autostart_enabled),
                pystray.MenuItem('Exit', self.exit_app)
            ]
            
            # Create the icon with menu
            self.icon = pystray.Icon("AppleBrightness", icon_image, "Apple Display Brightness", menu_items)
            
            # Start the icon in a separate thread
            threading.Thread(target=self.icon.run, daemon=True).start()
        except Exception as e:
            print(f"Error setting up system tray: {e}")
            # Fallback to just showing the GUI if tray fails
            self.show_window()
        
    def create_tray_icon(self):
        """Create a simple icon for the system tray"""
        # Create a simple square icon with a sun symbol
        width, height = 64, 64
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # Draw a sun
        center = width // 2
        radius = 15
        ray_length = 10
        
        # Draw circle
        draw.ellipse((center - radius, center - radius, 
                      center + radius, center + radius), 
                     fill=(255, 204, 0))
        
        # Draw rays
        for i in range(8):
            angle = i * 45  # degrees
            import math
            rad = math.radians(angle)
            x1 = center + (radius + 2) * math.cos(rad)
            y1 = center + (radius + 2) * math.sin(rad)
            x2 = center + (radius + ray_length) * math.cos(rad)
            y2 = center + (radius + ray_length) * math.sin(rad)
            draw.line((x1, y1, x2, y2), fill=(255, 204, 0), width=3)
        
        return image
        
    def show_window(self):
        """Show the brightness control window"""
        # Update the slider with current brightness
        self.brightness_slider.set(self.current_brightness)
        self.update_brightness_value(self.current_brightness)
        
        # Show and focus the window
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
    def hide_window(self):
        """Hide the window instead of closing it"""
        self.root.withdraw()
        
    def exit_app(self, icon=None, item=None):
        """Exit the application properly"""
        # Prevent multiple exit calls
        if self.exiting:
            return
            
        self.exiting = True
        
        # Save settings before exit
        self.save_settings()
        
        # Schedule icon stop to avoid SystemExit exception in callback
        if self.icon:
            # We need to stop the icon in a separate thread to avoid
            # SystemExit propagation in the callback context
            def stop_icon():
                try:
                    self.icon.stop()
                except:
                    pass
                    
            threading.Thread(target=stop_icon).start()
        
        # Schedule root destruction with slight delay 
        # to allow callback context to return normally
        def delayed_exit():
            try:
                self.root.after(100, self.root.destroy)
            except:
                pass
        
        # Schedule exit from main thread
        if threading.current_thread() is threading.main_thread():
            delayed_exit()
        else:
            self.root.after(0, delayed_exit)
        
    def save_settings(self):
        """Save current brightness setting to file"""
        try:
            settings = {
                'brightness': self.current_brightness,
                'autostart': self.autostart_enabled
            }
            
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f)
                
            print(f"Settings saved: {settings}")
        except Exception as e:
            print(f"Error saving settings: {e}")
            
    def load_settings(self):
        """Load brightness settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    
                self.current_brightness = settings.get('brightness', 250)
                self.autostart_enabled = settings.get('autostart', False)
                print(f"Loaded settings: brightness={self.current_brightness}%, autostart={self.autostart_enabled}")
        except Exception as e:
            print(f"Error loading settings: {e}")
            
    def get_startup_path(self):
        """Get the path to the startup shortcut"""
        try:
            startup_folder = shell.SHGetFolderPath(0, shellcon.CSIDL_STARTUP, 0, 0)
            shortcut_path = os.path.join(startup_folder, "AppleBrightnessControl.lnk")
            return shortcut_path
        except Exception as e:
            print(f"Error getting startup path: {e}")
            return os.path.join(os.environ.get('APPDATA', ''), 
                             r"Microsoft\Windows\Start Menu\Programs\Startup\AppleBrightnessControl.lnk")
        
    def check_autostart_enabled(self):
        """Check if autostart is enabled - separate from menu callback"""
        return os.path.exists(self.get_startup_path())
        
    def toggle_autostart(self, icon, item):
        """Toggle autostart with Windows - menu callback compatible"""
        try:
            shortcut_path = self.get_startup_path()
            
            # Toggle based on current state
            if self.autostart_enabled:
                # Remove from startup
                try:
                    if os.path.exists(shortcut_path):
                        os.remove(shortcut_path)
                    self.autostart_enabled = False
                    print("Removed from startup")
                except Exception as e:
                    print(f"Error removing from startup: {e}")
            else:
                # Add to startup by creating a shortcut
                try:
                    from win32com.client import Dispatch
                    
                    shell_obj = Dispatch('WScript.Shell')
                    shortcut = shell_obj.CreateShortCut(shortcut_path)
                    
                    # Get the path of the current script/executable
                    if getattr(sys, 'frozen', False):
                        # Running as compiled executable
                        target_path = sys.executable
                    else:
                        # Running as script
                        target_path = sys.executable
                        shortcut.Arguments = os.path.abspath(__file__)
                        
                    shortcut.TargetPath = target_path
                    shortcut.WorkingDirectory = os.path.dirname(target_path)
                    shortcut.Description = "Apple Display Brightness Control"
                    shortcut.Save()
                    
                    self.autostart_enabled = True
                    print(f"Added to startup: {shortcut_path}")
                except Exception as e:
                    print(f"Error adding to startup: {e}")
                    
            # Save settings after toggling
            self.save_settings()
            
            # Force update the system tray menu
            if self.icon:
                self.icon.update_menu()
        except Exception as e:
            print(f"Error toggling autostart: {e}")

def main():
    # Check for admin privileges - always require admin now
    if not is_admin():
        print("This application requires administrator privileges for display brightness control.")
        print("Requesting elevation...")
        
        # Show a message box before elevation prompt
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "Administrator Privileges Required", 
            "This application requires administrator privileges to control display brightness.\n"
            "Please allow elevation in the next prompt."
        )
        root.destroy()
        
        # Force admin elevation
        run_as_admin()
        return
        
    # Create and start the controller app
    app = BrightnessController()
    
    # Configure a clean exit when the window is closed by the OS
    def on_closing():
        app.exit_app()
        
    app.root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Set up signal handlers for clean exit
    try:
        import signal
        signal.signal(signal.SIGINT, lambda sig, frame: app.exit_app())
        signal.signal(signal.SIGTERM, lambda sig, frame: app.exit_app())
    except (ImportError, AttributeError):
        pass
    
    # Start the Tkinter main loop
    app.root.mainloop()

if __name__ == "__main__":
    main()
