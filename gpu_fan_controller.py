import sys
import platform
from ctypes import *
import time
import threading
import json
import os
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    import tkinter as tk
    from tkinter import simpledialog, messagebox, ttk
except ImportError:
    print("Required packages not found. Installing pystray and pillow...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    import tkinter as tk
    from tkinter import simpledialog, messagebox, ttk

class ADLFanSpeedValue(Structure):
    _fields_ = [
        ("Size", c_int),
        ("SpeedType", c_int),
        ("FanSpeed", c_int),
        ("Flags", c_int)
    ]

class ADLTemperature(Structure):
    _fields_ = [
        ("Size", c_int),
        ("Temperature", c_int)
    ]

def get_adl_dll():
    """Load and return the AMD ADL (AMD Display Library) DLL."""
    try:
        if platform.architecture()[0] == '64bit':
            adl_dll = cdll.LoadLibrary('atiadlxx.dll')
        else:
            adl_dll = cdll.LoadLibrary('atiadlxy.dll')
        return adl_dll
    except:
        print("Failed to load ADL library. Make sure AMD drivers are installed.")
        return None

def init_adl():
    """Initialize the ADL library."""
    adl = get_adl_dll()
    if not adl:
        return None
        
    # Define function prototypes
    ADL_MAIN_CONTROL_CREATE = adl.ADL_Main_Control_Create
    ADL_MAIN_CONTROL_CREATE.argtypes = [c_int]
    ADL_MAIN_CONTROL_CREATE.restype = c_int
    
    # Initialize ADL
    ADL_MAIN_CONTROL_CREATE(1)
    
    return adl

def get_fan_speed(adl, adapter_index=0):
    """Get the current fan speed of the GPU."""
    if not adl:
        return None
        
    # Define function prototype
    ADL_OVERDRIVE5_FANSPEED_GET = adl.ADL_Overdrive5_FanSpeed_Get
    ADL_OVERDRIVE5_FANSPEED_GET.argtypes = [c_int, c_int, POINTER(ADLFanSpeedValue)]
    ADL_OVERDRIVE5_FANSPEED_GET.restype = c_int
    
    # Create fan speed struct
    fan_speed = ADLFanSpeedValue()
    fan_speed.Size = sizeof(fan_speed)
    fan_speed.SpeedType = 1  # Percentage
    
    # Get fan speed
    result = ADL_OVERDRIVE5_FANSPEED_GET(adapter_index, 0, byref(fan_speed))
    if result != 0:
        print(f"Failed to get fan speed. Error code: {result}")
        return None
        
    return fan_speed.FanSpeed

def set_fan_speed(adl, speed_percent, adapter_index=0):
    """Set the GPU fan speed to a percentage (0-100)."""
    if not adl:
        return False
        
    # Bound the speed to 0-100%
    speed_percent = max(0, min(100, speed_percent))
    
    # Define function prototype
    ADL_OVERDRIVE5_FANSPEED_SET = adl.ADL_Overdrive5_FanSpeed_Set
    ADL_OVERDRIVE5_FANSPEED_SET.argtypes = [c_int, c_int, POINTER(ADLFanSpeedValue)]
    ADL_OVERDRIVE5_FANSPEED_SET.restype = c_int
    
    # Create fan speed struct
    fan_speed = ADLFanSpeedValue()
    fan_speed.Size = sizeof(fan_speed)
    fan_speed.SpeedType = 1  # Percentage
    fan_speed.FanSpeed = speed_percent
    fan_speed.Flags = 0
    
    # Set fan speed
    result = ADL_OVERDRIVE5_FANSPEED_SET(adapter_index, 0, byref(fan_speed))
    if result != 0:
        print(f"Failed to set fan speed. Error code: {result}")
        return False
        
    return True

def get_temperature(adl, adapter_index=0):
    """Get the current GPU temperature."""
    if not adl:
        return None
        
    # Define function prototype
    ADL_OVERDRIVE5_TEMPERATURE_GET = adl.ADL_Overdrive5_Temperature_Get
    ADL_OVERDRIVE5_TEMPERATURE_GET.argtypes = [c_int, c_int, POINTER(ADLTemperature)]
    ADL_OVERDRIVE5_TEMPERATURE_GET.restype = c_int
    
    # Create temperature struct
    temperature = ADLTemperature()
    temperature.Size = sizeof(temperature)
    
    # Get temperature
    result = ADL_OVERDRIVE5_TEMPERATURE_GET(adapter_index, 0, byref(temperature))
    if result != 0:
        print(f"Failed to get temperature. Error code: {result}")
        return None
        
    # Temperature is reported in millidegrees Celsius
    return temperature.Temperature / 1000.0

def disable_fan_control(adl, adapter_index=0):
    """Disable manual fan control and return to automatic fan management."""
    if not adl:
        return False
        
    # Define function prototype
    ADL_OVERDRIVE5_FANSPEEDTODEFAULT_SET = adl.ADL_Overdrive5_FanSpeedToDefault_Set
    ADL_OVERDRIVE5_FANSPEEDTODEFAULT_SET.argtypes = [c_int, c_int]
    ADL_OVERDRIVE5_FANSPEEDTODEFAULT_SET.restype = c_int
    
    # Reset fan control to default/automatic
    result = ADL_OVERDRIVE5_FANSPEEDTODEFAULT_SET(adapter_index, 0)
    if result != 0:
        print(f"Failed to reset fan control to automatic mode. Error code: {result}")
        return False
        
    return True

class FanCurve:
    """
    Fan curve manager for defining temperature to fan speed relationships
    """
    def __init__(self, name="Default", points=None):
        self.name = name
        self.points = points or [(30, 30), (50, 40), (70, 60), (80, 80), (90, 100)]
        # Ensure points are sorted by temperature
        self.points.sort(key=lambda p: p[0])
        
    def get_fan_speed(self, temperature):
        """Get the appropriate fan speed for the given temperature based on the curve"""
        if temperature is None:
            return None
            
        # If temperature is below the first point
        if temperature <= self.points[0][0]:
            return self.points[0][1]
            
        # If temperature is above the last point
        if temperature >= self.points[-1][0]:
            return self.points[-1][1]
            
        # Find the two points to interpolate between
        for i in range(len(self.points) - 1):
            t1, f1 = self.points[i]
            t2, f2 = self.points[i + 1]
            
            if t1 <= temperature <= t2:
                # Linear interpolation between the two points
                ratio = (temperature - t1) / (t2 - t1)
                return f1 + ratio * (f2 - f1)
                
        # Fallback (should never reach here)
        return 50

def save_curve(curve, filename="fan_curve.json"):
    """Save a fan curve to a JSON file"""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
    os.makedirs(config_dir, exist_ok=True)
    file_path = os.path.join(config_dir, filename)
    
    with open(file_path, 'w') as f:
        json.dump({"name": curve.name, "points": curve.points}, f)
    
    return file_path

def load_curve(filename="fan_curve.json"):
    """Load a fan curve from a JSON file"""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
    file_path = os.path.join(config_dir, filename)
    
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return FanCurve(data.get("name", "Loaded"), data.get("points", []))
    except (json.JSONDecodeError, IOError):
        return None

def temperature_control(adl, target_temp, min_fan=30, max_fan=100):
    """
    Control fan speed to maintain a target temperature.
    Returns a function that can be called to get the appropriate fan speed.
    Uses an adaptive control algorithm that becomes less aggressive over time
    when the temperature is stable.
    """
    last_fan_speed = min_fan
    temp_history = []
    history_max_size = 10  # Store last 10 temperature readings
    
    # Settings for adaptation
    aggressive_mode = True  # Start in aggressive mode
    stable_threshold = 2.0  # °C variation considered stable
    stable_counter = 0
    stable_required = 6     # Readings required to consider temp stable
    
    def get_fan_speed_for_temp(current_temp):
        nonlocal last_fan_speed, aggressive_mode, stable_counter, temp_history
        
        if current_temp is None:
            return last_fan_speed
        
        # Update temperature history
        temp_history.append(current_temp)
        if len(temp_history) > history_max_size:
            temp_history.pop(0)
        
        # Check if temperature is stable
        if len(temp_history) >= 4:  # Need at least 4 readings
            temp_variation = max(temp_history) - min(temp_history)
            
            # If temperature is stable around target
            if abs(current_temp - target_temp) < 3.0 and temp_variation < stable_threshold:
                stable_counter += 1
                if stable_counter >= stable_required and aggressive_mode:
                    aggressive_mode = False
                    print("Temperature stable. Switching to gentle control mode.")
            else:
                stable_counter = 0
                if not aggressive_mode and (abs(current_temp - target_temp) > 5.0 or temp_variation > 4.0):
                    aggressive_mode = True
                    print("Temperature unstable. Switching to aggressive control mode.")
        
        # Calculate temperature difference from target
        temp_diff = current_temp - target_temp
        
        # Set control parameters based on mode
        if aggressive_mode:
            # Aggressive parameters
            over_target_gain = 2.5   # % per °C over target
            under_target_gain = 1.5  # % per °C under target
            min_adjustment = 3       # Minimum adjustment to make
        else:
            # Gentle parameters
            over_target_gain = 1.5   # % per °C over target
            under_target_gain = 0.8  # % per °C under target
            min_adjustment = 1       # Smaller adjustments when stable
        
        # Calculate fan speed adjustment
        if temp_diff > 0:
            # If hotter than target, increase fan speed
            adjustment = max(min_adjustment, int(temp_diff * over_target_gain))
            
            # More aggressive if moving away from target quickly
            if len(temp_history) >= 3 and temp_history[-1] > temp_history[-3]:
                adjustment = int(adjustment * 1.5)
                
            new_fan = min(max_fan, last_fan_speed + adjustment)
        else:
            # If cooler than target, decrease fan speed
            adjustment = max(min_adjustment, int(abs(temp_diff) * under_target_gain))
            
            # Less aggressive when decreasing - prevent oscillation
            if aggressive_mode:
                adjustment = int(adjustment * 0.7)
            else:
                adjustment = int(adjustment * 0.5)
                
            new_fan = max(min_fan, last_fan_speed - adjustment)
        
        # Prevent frequent small changes to avoid noise
        if abs(new_fan - last_fan_speed) >= 2 or abs(temp_diff) > 3:
            last_fan_speed = new_fan
            
        return last_fan_speed
    
    return get_fan_speed_for_temp

def create_icon_image(temp, fan_speed):
    """Create an image for the system tray icon with temperature and fan speed."""
    # Create a blank image with white background
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Try to use a system font
    try:
        font = ImageFont.truetype("Arial", 12)
    except IOError:
        # Fall back to default
        font = ImageFont.load_default()
    
    # Choose color based on temperature
    if temp is None:
        color = (128, 128, 128)  # Gray if unknown
    elif temp > 80:
        color = (255, 0, 0)      # Red if hot
    elif temp > 70:
        color = (255, 165, 0)    # Orange if warm
    else:
        color = (0, 255, 0)      # Green if cool
    
    # Draw temperature and fan speed
    temp_str = f"{temp:.0f}°C" if temp is not None else "??°C"
    fan_str = f"{fan_speed}%" if fan_speed is not None else "??%"
    
    draw.text((5, 10), temp_str, font=font, fill=color)
    draw.text((5, 35), fan_str, font=font, fill=(255, 255, 255))
    
    return image

def apply_fan_curve(adl, curve, interval=2):
    """Apply a fan curve continuously until interrupted"""
    try:
        print(f"Applying fan curve: {curve.name}")
        print("Temperature -> Fan Speed:")
        for temp, fan in curve.points:
            print(f"  {temp}°C -> {fan}%")
        
        print("\nMonitoring temperature and adjusting fan speed...")
        print("Press Ctrl+C to stop")
        
        while True:
            temp = get_temperature(adl)
            if temp is not None:
                fan_speed = int(curve.get_fan_speed(temp))
                set_fan_speed(adl, fan_speed)
                print(f"\rTemp: {temp:.1f}°C | Fan: {fan_speed}%", end="")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping fan curve application")

def apply_temp_limit(adl, target_temp, min_fan=30, max_fan=100, interval=2):
    """Maintain a target temperature by adjusting fan speed"""
    try:
        print(f"Maintaining target temperature: {target_temp}°C")
        print(f"Fan speed range: {min_fan}% - {max_fan}%")
        
        temp_controller = temperature_control(adl, target_temp, min_fan, max_fan)
        
        print("\nMonitoring temperature and adjusting fan speed...")
        print("Press Ctrl+C to stop")
        
        while True:
            temp = get_temperature(adl)
            if temp is not None:
                fan_speed = temp_controller(temp)
                set_fan_speed(adl, fan_speed)
                print(f"\rTemp: {temp:.1f}°C | Fan: {fan_speed}%", end="")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping temperature control")

# Global reference to prevent garbage collection
_root_window = None

class FanCurveDialog(tk.Toplevel):
    """Dialog window for setting up a fan curve"""
    def __init__(self, parent, current_curve=None, callback=None):
        tk.Toplevel.__init__(self, parent)
        self.title("Fan Curve Setup")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.callback = callback
        self.parent = parent
        
        # Center the dialog on the screen
        w = 320
        h = 270
        ws = parent.winfo_screenwidth()
        hs = parent.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))
        
        # Set initial values
        self.current_curve = current_curve or FanCurve()
        self.points = []
        for i in range(5):
            if i < len(self.current_curve.points):
                self.points.append(list(self.current_curve.points[i]))
            else:
                self.points.append([0, 0])
        
        # Create widgets
        self.create_widgets()
        
        # Bring to front
        self.lift()
        self.focus_force()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Curve name
        ttk.Label(main_frame, text="Curve Name:").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        self.name_var = tk.StringVar(value=self.current_curve.name)
        ttk.Entry(main_frame, textvariable=self.name_var, width=20).grid(row=0, column=1, columnspan=3, sticky=tk.W+tk.E, pady=(0, 10))
        
        # Headers
        ttk.Label(main_frame, text="Temperature (°C)").grid(row=1, column=1, padx=5)
        ttk.Label(main_frame, text="Fan Speed (%)").grid(row=1, column=2, padx=5)
        
        # Point inputs
        self.temp_vars = []
        self.fan_vars = []
        for i in range(5):
            ttk.Label(main_frame, text=f"Point {i+1}:").grid(row=i+2, column=0, sticky=tk.W, pady=2)
            
            temp_var = tk.IntVar(value=self.points[i][0])
            fan_var = tk.IntVar(value=self.points[i][1])
            
            self.temp_vars.append(temp_var)
            self.fan_vars.append(fan_var)
            
            temp_entry = ttk.Entry(main_frame, textvariable=temp_var, width=5)
            fan_entry = ttk.Entry(main_frame, textvariable=fan_var, width=5)
            
            temp_entry.grid(row=i+2, column=1, padx=5, pady=2)
            fan_entry.grid(row=i+2, column=2, padx=5, pady=2)
            
        # Message
        ttk.Label(main_frame, text="Note: Points with zero temperature will be ignored").grid(
            row=7, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
            
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=8, column=0, columnspan=3, pady=(10, 0))
        
        ttk.Button(button_frame, text="OK", command=self.on_ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=10).pack(side=tk.LEFT, padx=5)
        
    def on_ok(self):
        # Validate and collect points
        valid_points = []
        for i in range(5):
            try:
                temp = self.temp_vars[i].get()
                fan = self.fan_vars[i].get()
                if temp > 0:  # Skip points with zero temperature
                    if 0 <= temp <= 110 and 0 <= fan <= 100:
                        valid_points.append([temp, fan])
                    else:
                        messagebox.showerror("Invalid Values", 
                                            f"Point {i+1} has invalid values.\n"
                                            "Temperature must be 0-110°C\n"
                                            "Fan speed must be 0-100%")
                        return
            except tk.TclError:
                pass  # Skip empty entries
        
        # Check if we have enough points
        if len(valid_points) < 2:
            messagebox.showerror("Not Enough Points", "You need at least 2 valid points to create a curve.")
            return
            
        name = self.name_var.get() or "Custom"
        result = FanCurve(name, valid_points)
        if self.callback:
            self.callback(result)
        self.destroy()
        
    def on_cancel(self):
        if self.callback:
            self.callback(None)
        self.destroy()

class TempControlDialog(tk.Toplevel):
    """Dialog window for setting up temperature control"""
    def __init__(self, parent, current_target=70, current_min=30, current_max=100, callback=None):
        tk.Toplevel.__init__(self, parent)
        self.title("Temperature Control Setup")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.callback = callback
        self.parent = parent
        
        # Center the dialog on the screen
        w = 400
        h = 180
        ws = parent.winfo_screenwidth()
        hs = parent.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))
        
        # Set initial values
        self.current_target = current_target
        self.current_min = current_min
        self.current_max = current_max
        
        # Create widgets
        self.create_widgets()
        
        # Bring to front
        self.lift()
        self.focus_force()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Target temperature
        ttk.Label(main_frame, text="Target Temperature (°C):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.target_var = tk.IntVar(value=self.current_target)
        temp_scale = ttk.Scale(main_frame, from_=40, to=90, variable=self.target_var, 
                              orient=tk.HORIZONTAL, length=200)
        temp_scale.grid(row=0, column=1, sticky=tk.W+tk.E, pady=5)
        temp_scale.bind("<Motion>", self.update_target_label)
        temp_scale.bind("<ButtonRelease-1>", self.update_target_label)
        self.target_label = ttk.Label(main_frame, text=str(self.current_target))
        self.target_label.grid(row=0, column=2, padx=5)
        
        # Min fan speed
        ttk.Label(main_frame, text="Minimum Fan Speed (%):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.min_var = tk.IntVar(value=self.current_min)
        min_scale = ttk.Scale(main_frame, from_=0, to=100, variable=self.min_var,
                             orient=tk.HORIZONTAL, length=200)
        min_scale.grid(row=1, column=1, sticky=tk.W+tk.E, pady=5)
        min_scale.bind("<Motion>", self.update_min_label)
        min_scale.bind("<ButtonRelease-1>", self.update_min_label)
        self.min_label = ttk.Label(main_frame, text=str(self.current_min))
        self.min_label.grid(row=1, column=2, padx=5)
        
        # Max fan speed
        ttk.Label(main_frame, text="Maximum Fan Speed (%):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.max_var = tk.IntVar(value=self.current_max)
        max_scale = ttk.Scale(main_frame, from_=0, to=100, variable=self.max_var,
                             orient=tk.HORIZONTAL, length=200)
        max_scale.grid(row=2, column=1, sticky=tk.W+tk.E, pady=5)
        max_scale.bind("<Motion>", self.update_max_label)
        max_scale.bind("<ButtonRelease-1>", self.update_max_label)
        self.max_label = ttk.Label(main_frame, text=str(self.current_max))
        self.max_label.grid(row=2, column=2, padx=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        
        ttk.Button(button_frame, text="OK", command=self.on_ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=10).pack(side=tk.LEFT, padx=5)
    
    def update_target_label(self, event=None):
        self.target_label.config(text=str(self.target_var.get()))
    
    def update_min_label(self, event=None):
        self.min_label.config(text=str(self.min_var.get()))
        if self.min_var.get() > self.max_var.get():
            self.max_var.set(self.min_var.get())
            self.update_max_label()
    
    def update_max_label(self, event=None):
        self.max_label.config(text=str(self.max_var.get()))
        if self.max_var.get() < self.min_var.get():
            self.min_var.set(self.max_var.get())
            self.update_min_label()
        
    def on_ok(self):
        target = self.target_var.get()
        min_fan = self.min_var.get()
        max_fan = self.max_var.get()
        
        # Ensure max >= min
        if max_fan < min_fan:
            messagebox.showerror("Invalid Values", "Maximum fan speed must be greater than or equal to minimum fan speed.")
            return
            
        result = (target, min_fan, max_fan)
        if self.callback:
            self.callback(result)
        self.destroy()
        
    def on_cancel(self):
        if self.callback:
            self.callback(None)
        self.destroy()

def safe_tk_message(title, message, is_question=False):
    """Display a tkinter message box safely in a separate thread"""
    try:
        if is_question:
            return messagebox.askyesno(title, message)
        else:
            messagebox.showinfo(title, message)
            return None
    except Exception as e:
        print(f"Error displaying message: {e}")
        return False if is_question else None

def monitor_in_system_tray(adl):
    """Monitor GPU temperature and fan speed in the system tray."""
    global _root_window
    
    # Initial readings
    temp = get_temperature(adl)
    fan_speed = get_fan_speed(adl)
    
    # Create a hidden root window for dialogs
    root = tk.Tk()
    _root_window = root  # Keep a global reference
    root.withdraw()  # Hide the root window
    
    # Initialize dialog states
    curve_dialog_open = False
    temp_dialog_open = False
    
    # Load saved fan curve if available
    saved_curve = load_curve()
    curve_mode = False
    temp_limit_mode = False
    current_curve = saved_curve or FanCurve()
    target_temp = 70
    min_fan = 30
    max_fan = 100
    
    # Function to update the icon
    def update_icon():
        nonlocal temp, fan_speed
        while True:
            temp = get_temperature(adl)
            fan_speed = get_fan_speed(adl)
            
            # Apply curve if in curve mode
            if curve_mode and temp is not None:
                new_fan = int(current_curve.get_fan_speed(temp))
                if new_fan != fan_speed:
                    set_fan_speed(adl, new_fan)
                    fan_speed = new_fan
            
            # Apply temp limit if in temp limit mode
            if temp_limit_mode and temp is not None:
                new_fan = temp_controller(temp)
                if new_fan != fan_speed:
                    set_fan_speed(adl, new_fan)
                    fan_speed = new_fan
            
            if icon is not None and icon.visible:
                try:
                    icon.icon = create_icon_image(temp, fan_speed)
                    status = "GPU: {:.1f}°C | Fan: {}%".format(temp, fan_speed)
                    
                    if curve_mode:
                        status += f" | Curve: {current_curve.name}"
                    elif temp_limit_mode:
                        status += f" | Target: {target_temp}°C"
                        
                    icon.title = status
                except Exception as e:
                    print(f"Error updating icon: {e}")
                    
            # Process tkinter events to prevent freezing
            try:
                root.update_idletasks()
                root.update()
            except:
                # Tk might be closed already
                pass
                
            time.sleep(0.5)  # Update more frequently to handle UI events
    
    # Fan curve setup dialog callback
    def on_curve_dialog_complete(result):
        nonlocal current_curve, curve_mode, curve_dialog_open
        curve_dialog_open = False
        
        if result:
            current_curve = result
            save_curve(current_curve)
            
            # Ask to enable the curve (in main thread)
            def ask_enable():
                nonlocal curve_mode, temp_limit_mode
                if safe_tk_message("Fan Curve", 
                                   f"Fan curve '{current_curve.name}' has been saved.\n\n"
                                   "Do you want to enable it now?",
                                   is_question=True):
                    curve_mode = True
                    temp_limit_mode = False
            
            # Schedule in main thread
            root.after(100, ask_enable)
    
    # Fan curve setup dialog 
    def setup_fan_curve():
        nonlocal curve_dialog_open
        if curve_dialog_open:
            return  # Prevent multiple dialogs
            
        curve_dialog_open = True
        try:
            FanCurveDialog(root, current_curve, callback=on_curve_dialog_complete)
        except Exception as e:
            curve_dialog_open = False
            print(f"Error creating fan curve dialog: {e}")
    
    # Temperature limit setup callback
    def on_temp_dialog_complete(result):
        nonlocal target_temp, temp_limit_mode, temp_controller, min_fan, max_fan, temp_dialog_open
        temp_dialog_open = False
        
        if result:
            target_temp, min_fan, max_fan = result
            temp_controller = temperature_control(adl, target_temp, min_fan, max_fan)
            
            # Ask to enable temperature control (in main thread)
            def ask_enable():
                nonlocal temp_limit_mode, curve_mode
                if safe_tk_message("Temperature Control", 
                                   f"Target temperature set to {target_temp}°C\n"
                                   f"Fan range: {min_fan}% - {max_fan}%\n\n"
                                   "Do you want to enable temperature control now?",
                                   is_question=True):
                    temp_limit_mode = True
                    curve_mode = False
            
            # Schedule in main thread
            root.after(100, ask_enable)
    
    # Temperature limit setup
    def setup_temp_limit():
        nonlocal temp_dialog_open
        if temp_dialog_open:
            return  # Prevent multiple dialogs
            
        temp_dialog_open = True
        try:
            TempControlDialog(root, target_temp, min_fan, max_fan, callback=on_temp_dialog_complete)
        except Exception as e:
            temp_dialog_open = False
            print(f"Error creating temperature dialog: {e}")
    
    # Define menu items and callbacks
    def set_speed_30():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = temp_limit_mode = False
        set_fan_speed(adl, 30)
    
    def set_speed_50():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = temp_limit_mode = False
        set_fan_speed(adl, 50)
    
    def set_speed_70():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = temp_limit_mode = False
        set_fan_speed(adl, 70)
    
    def set_speed_100():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = temp_limit_mode = False
        set_fan_speed(adl, 100)
    
    def toggle_curve():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = not curve_mode
        if curve_mode:
            temp_limit_mode = False
    
    def toggle_temp_limit():
        nonlocal temp_limit_mode, curve_mode, temp_controller
        temp_limit_mode = not temp_limit_mode
        if temp_limit_mode:
            curve_mode = False
            if not temp_controller:
                temp_controller = temperature_control(adl, target_temp, min_fan, max_fan)
    
    def configure_curve():
        root.after(0, setup_fan_curve)  # Schedule in main thread
    
    def configure_temp():
        root.after(0, setup_temp_limit)  # Schedule in main thread
    
    def reset_to_auto():
        nonlocal curve_mode, temp_limit_mode
        curve_mode = temp_limit_mode = False
        disable_fan_control(adl)
    
    def exit_app():
        print("Exiting application...")
        root.after(0, root.quit)  # Schedule quit in the main thread
        if icon and icon.visible:
            icon.stop()
    
    # Initialize temperature controller
    temp_controller = temperature_control(adl, target_temp, min_fan, max_fan)
    
    # Create and display the icon with expanded menu
    menu = (
        pystray.MenuItem("Set Fan 30%", set_speed_30),
        pystray.MenuItem("Set Fan 50%", set_speed_50),
        pystray.MenuItem("Set Fan 70%", set_speed_70),
        pystray.MenuItem("Set Fan 100%", set_speed_100),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Use Fan Curve ({current_curve.name})", toggle_curve, checked=lambda _: curve_mode),
        pystray.MenuItem("Configure Fan Curve", configure_curve),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Maintain {target_temp}°C", toggle_temp_limit, checked=lambda _: temp_limit_mode),
        pystray.MenuItem("Configure Temp Target", configure_temp),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Auto Control", reset_to_auto),
        pystray.MenuItem("Exit", exit_app)
    )
    
    # Create icon
    icon = pystray.Icon("GPU Monitor", 
                       create_icon_image(temp, fan_speed), 
                       f"GPU: {temp:.1f}°C | Fan: {fan_speed}%",
                       menu)
    
    # Start the update thread
    update_thread = threading.Thread(target=update_icon, daemon=True)
    update_thread.start()
    
    # Run the icon in its own thread to avoid blocking the main thread
    icon_thread = threading.Thread(target=icon.run, daemon=True)
    icon_thread.start()
    
    try:
        # Start the main loop - this should not block
        print("System tray icon activated. Look for the icon in your system tray.")
        root.mainloop()
    except KeyboardInterrupt:
        print("\nExiting due to keyboard interrupt...")
    except Exception as e:
        print(f"Error in main loop: {e}")
    finally:
        # Clean up
        if icon and icon.visible:
            try:
                icon.stop()
            except:
                pass

def main():
    print("AMD Radeon 5700 Fan Controller")
    adl = init_adl()
    
    if not adl:
        print("Failed to initialize ADL. Exiting.")
        return
    
    try:
        # Show current stats
        current_fan = get_fan_speed(adl)
        current_temp = get_temperature(adl)
        
        print(f"Current fan speed: {current_fan}%")
        print(f"Current temperature: {current_temp:.1f}°C")
        
        # Check command line arguments
        if len(sys.argv) > 1:
            # Check for disable command
            if sys.argv[1].lower() in ["disable", "auto", "default"]:
                print("Disabling manual fan control, returning to automatic mode...")
                if disable_fan_control(adl):
                    print("Successfully returned to automatic fan control")
                else:
                    print("Failed to return to automatic fan control")
            # Check for fan curve command
            elif sys.argv[1].lower() == "curve":
                # Load curve or create default
                curve = load_curve()
                if not curve:
                    print("No saved fan curve found. Using default curve.")
                    curve = FanCurve()
                apply_fan_curve(adl, curve)
            # Check for temperature limit command
            elif sys.argv[1].lower() in ["temp", "limit", "target"]:
                target = 70  # Default
                if len(sys.argv) > 2 and sys.argv[2].isdigit():
                    target = int(sys.argv[2])
                    target = max(40, min(90, target))  # Limit between 40-90°C
                apply_temp_limit(adl, target)
            # Check for fan speed setting
            elif sys.argv[1].isdigit():
                speed = int(sys.argv[1])
                if 0 <= speed <= 100:
                    print(f"Setting fan speed to {speed}%")
                    if set_fan_speed(adl, speed):
                        print(f"Fan speed successfully set to {speed}%")
                    else:
                        print("Failed to set fan speed")
                else:
                    print("Error: Fan speed must be between 0 and 100.")
            else:
                print("Error: Unrecognized command")
                print("\nUsage:")
                print("  python gpu_fan_controller.py         - Monitor in system tray")
                print("  python gpu_fan_controller.py SPEED   - Set fan speed (0-100)")
                print("  python gpu_fan_controller.py disable - Return to automatic control")
                print("  python gpu_fan_controller.py curve   - Apply saved fan curve")
                print("  python gpu_fan_controller.py temp [TEMP] - Maintain target temperature (default 70°C)")
        else:
            print("\nStarting system tray monitoring...")
            print("Right-click the icon to access fan control options")
            print("Press Ctrl+C in this window to exit")
            monitor_in_system_tray(adl)
    
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        # Clean up
        if adl:
            adl.ADL_Main_Control_Destroy()
            print("ADL resources released.")

if __name__ == "__main__":
    main()
