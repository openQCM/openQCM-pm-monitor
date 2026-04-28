"""Shared constants for openQCM Aerosol project."""

# =============================================================================
# CRYSTAL CONFIGURATIONS
# =============================================================================

CRYSTAL_OPTIONS = {
    '5 MHz': {
        'center_freq': 5000000,
        'search_range': 50000,
        'search_step': 100,
        'fine_range': 5000,
        'fine_step': 1
    },
    '10 MHz': {
        'center_freq': 10000000,
        'search_range': 100000,
        'search_step': 200,
        'fine_range': 5000,
        'fine_step': 1
    },
    'Custom': {
        'center_freq': 5000000,
        'search_range': 50000,
        'search_step': 100,
        'fine_range': 5000,
        'fine_step': 1
    }
}

# =============================================================================
# COLOR PALETTES
# =============================================================================

# Active theme: "dark" or "native"
THEME = "native"

COLORS_DARK = {
    'background':     '#1e1e2e',
    'surface':        '#282838',
    'border':         '#3a3a4a',
    'text':           '#cdd6f4',
    'text_dim':       '#7f849c',
    'accent':         '#89b4fa',
    'accent_hover':   '#74c7ec',
    'red':            '#f38ba8',
    'green':          '#a6e3a1',
    'yellow':         '#f9e2af',
    'primary':        '#89b4fa',
    'primary_dark':   '#74c7ec',
    'secondary':      '#a6e3a1',
    'secondary_dark': '#94d990',
    'error':          '#f38ba8',
    'error_dark':     '#e06c8a',
    'warning':        '#f9e2af',
    'info':           '#94e2d5',
    'temperature':    '#f38ba8',
    'text_primary':   '#cdd6f4',
    'text_secondary': '#7f849c',
    'text_disabled':  '#45475a',
    'divider':        '#3a3a4a',
}

COLORS_NATIVE = {
    'background':     '#f5f5f5',
    'surface':        '#ffffff',
    'border':         '#d0d0d0',
    'text':           '#1a1a1a',
    'text_dim':       '#666666',
    'accent':         '#2068d0',
    'accent_hover':   '#1a56b0',
    'red':            '#d03030',
    'green':          '#208040',
    'yellow':         '#b08020',
    'primary':        '#2068d0',
    'primary_dark':   '#1a56b0',
    'secondary':      '#208040',
    'secondary_dark': '#1a6830',
    'error':          '#d03030',
    'error_dark':     '#b02020',
    'warning':        '#d0a020',
    'info':           '#1090a0',
    'temperature':    '#d03030',
    'text_primary':   '#1a1a1a',
    'text_secondary': '#666666',
    'text_disabled':  '#b0b0b0',
    'divider':        '#d0d0d0',
}

COLORS = COLORS_DARK if THEME == "dark" else COLORS_NATIVE

# =============================================================================
# QCM CONSTANTS
# =============================================================================

SAUERBREY_CONSTANT_5MHZ = 17.7e-9
SAUERBREY_CONSTANT_10MHZ = 4.42e-9
QUARTZ_AREA_CM2 = 0.196

# Flow calibration defaults
OUTLET_DIAMETER_MM = 4.0          # diametro foro uscita (mm)
FLOW_CALIBRATION_FACTOR = 1.0     # K_cal (L/min per m/s), da calibrazione esterna

# Rolling display window for real-time plots (seconds)
# Only display buffers use this — CSV logging keeps the full session history.
MONITOR_WINDOW_SECONDS = 3600     # 1 hour (production)

# =============================================================================
# SIGNAL PROCESSING CONSTANTS (from openQCM Next)
# =============================================================================

# Savitzky-Golay filter for sweep amplitude smoothing
SG_WINDOW_SIZE = 13       # Window size (must be odd)
SG_ORDER = 3              # Polynomial order

# Spline smoothing (applied after SG filter, same number of points)
SPLINE_FACTOR = 1         # Smoothing factor for UnivariateSpline (from openQCM Next)

# Temporal smoothing (ring buffer with trimmed mean)
TEMPORAL_BUFFER_SIZE = 10          # Number of sweeps to accumulate before smoothing kicks in
