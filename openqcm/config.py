#!/usr/bin/env python3
"""
OpenQCM Configuration File
=========================

Configuration settings for different openQCM setups and applications.
Modify these parameters according to your specific hardware and requirements.

Author: Novaetech S.r.l. / openQCM Team
"""

# ===== SERIAL COMMUNICATION SETTINGS =====
SERIAL_CONFIG = {
    # Default ports for different operating systems
    'default_ports': {
        'linux': '/dev/ttyACM0',
        'darwin': '/dev/tty.usbmodem',  # macOS
        'windows': 'COM3'
    },
    
    # Communication parameters
    'baudrate': 115200,
    'timeout': 5.0,
    'connection_retry_count': 3,
    'connection_retry_delay': 2.0
}

# ===== CRYSTAL-SPECIFIC CONFIGURATIONS =====
CRYSTAL_CONFIGS = {
    '5MHz_standard': {
        'center_freq': 5000000,
        'search_range': 50000,      # ±50 kHz
        'search_step': 100,         # 100 Hz steps for peak detection
        'fine_range': 10000,        # ±10 kHz for fine sweep  
        'fine_step': 10,            # 10 Hz steps for fine sweep
        'ultra_fine_step': 1        # 1 Hz for ultra-high resolution
    },
    
    '5MHz_high_q': {
        'center_freq': 5000000,
        'search_range': 30000,      # Narrower search for high-Q crystals
        'search_step': 50,          # Finer search steps
        'fine_range': 5000,         # ±5 kHz fine sweep
        'fine_step': 5,             # 5 Hz fine steps
        'ultra_fine_step': 1
    },
    
    '10MHz_standard': {
        'center_freq': 10000000,
        'search_range': 100000,     # ±100 kHz (higher frequencies need wider search)
        'search_step': 200,         # 200 Hz steps
        'fine_range': 20000,        # ±20 kHz fine sweep
        'fine_step': 20,            # 20 Hz fine steps
        'ultra_fine_step': 2        # 2 Hz ultra-fine
    },
    
    '15MHz_standard': {
        'center_freq': 15000000,
        'search_range': 150000,     # ±150 kHz
        'search_step': 300,         # 300 Hz steps
        'fine_range': 30000,        # ±30 kHz fine sweep
        'fine_step': 30,            # 30 Hz fine steps  
        'ultra_fine_step': 3        # 3 Hz ultra-fine
    },
    
    'custom': {
        'center_freq': 5000000,     # Modify as needed
        'search_range': 50000,      # Modify as needed
        'search_step': 100,         # Modify as needed
        'fine_range': 10000,        # Modify as needed
        'fine_step': 10,            # Modify as needed
        'ultra_fine_step': 1        # Modify as needed
    }
}

# ===== MEASUREMENT SETTINGS =====
MEASUREMENT_CONFIG = {
    # Peak detection algorithm parameters
    'peak_detection': {
        'height_threshold': 0.8,        # Minimum peak height (0.0-1.0)
        'distance_factor': 0.1,         # Minimum distance between peaks (fraction of data length)
        'smoothing_window_factor': 10,  # Smoothing window size (data_length // factor)
        'smoothing_polynomial': 3       # Polynomial order for Savitzky-Golay filter
    },
    
    # Quality factor calculation
    'q_factor': {
        'method': 'half_power',         # 'half_power' or 'full_width_half_max'
        'fallback_q': 1000             # Default Q if calculation fails
    },
    
    # Continuous monitoring
    'monitoring': {
        'default_duration_minutes': 30,
        'default_interval_seconds': 60,
        'quick_sweep_range': 1000,      # ±1 kHz for monitoring sweeps
        'quick_sweep_step': 20          # 20 Hz steps for speed
    }
}

# ===== PLOTTING CONFIGURATION =====
PLOT_CONFIG = {
    'figure_size': (12, 8),
    'dpi': 300,
    'amplitude_color': 'blue',
    'phase_color': 'green',
    'resonance_marker_color': 'red',
    'resonance_marker_style': '--',
    'grid_alpha': 0.3,
    'line_width': 1.5,
    
    # Font sizes
    'title_fontsize': 14,
    'label_fontsize': 12,
    'tick_fontsize': 10,
    'legend_fontsize': 10
}

# ===== FILE EXPORT SETTINGS =====
EXPORT_CONFIG = {
    'default_format': 'both',          # 'json', 'csv', or 'both'
    'timestamp_format': '%Y%m%d_%H%M%S',
    'csv_separator': ',',
    'json_indent': 2,
    
    # Default file prefixes
    'prefixes': {
        'sweep': 'qcm_sweep',
        'monitoring': 'qcm_monitoring',
        'multi_crystal': 'qcm_multi_crystal',
        'high_resolution': 'qcm_high_res'
    }
}

# ===== APPLICATION-SPECIFIC PRESETS =====
APPLICATION_PRESETS = {
    'biosensing': {
        'description': 'High-sensitivity biosensing applications',
        'crystal_config': '5MHz_high_q',
        'measurement_priority': 'accuracy',
        'recommended_averaging': 1000,  # Increase averaging in firmware
        'monitoring_interval': 30       # 30 second intervals
    },
    
    'electrochemistry': {
        'description': 'Electrochemical measurements with QCM-D',
        'crystal_config': '5MHz_standard',
        'measurement_priority': 'speed',
        'recommended_averaging': 500,
        'monitoring_interval': 10       # 10 second intervals for fast processes
    },
    
    'material_characterization': {
        'description': 'Material deposition and characterization',
        'crystal_config': '10MHz_standard',
        'measurement_priority': 'resolution',
        'recommended_averaging': 750,
        'monitoring_interval': 60       # 1 minute intervals
    },
    
    'quality_control': {
        'description': 'Fast quality control measurements',
        'crystal_config': '5MHz_standard',
        'measurement_priority': 'speed',
        'recommended_averaging': 250,   # Reduce averaging for speed
        'monitoring_interval': 5        # 5 second intervals
    }
}

# ===== TROUBLESHOOTING PRESETS =====
TROUBLESHOOTING = {
    'weak_signal': {
        'description': 'For crystals with weak resonance signals',
        'search_range_multiplier': 2.0,    # Double the search range
        'search_step_divisor': 2,           # Halve the search step (finer)
        'peak_height_threshold': 0.6,      # Lower threshold
        'smoothing_aggressive': True
    },
    
    'noisy_signal': {
        'description': 'For noisy environments',
        'smoothing_window_factor': 5,      # More aggressive smoothing
        'averaging_increase': 2.0,          # Suggest doubling firmware averaging
        'peak_distance_factor': 0.2        # Larger minimum distance between peaks
    },
    
    'multiple_resonances': {
        'description': 'For crystals with multiple resonance modes',
        'peak_detection_method': 'all_peaks',
        'distance_factor': 0.05,           # Smaller minimum distance
        'height_threshold': 0.9            # Higher threshold to select main peak
    }
}


def get_crystal_config(crystal_type='5MHz_standard'):
    """
    Get configuration for specific crystal type
    
    Args:
        crystal_type: Key from CRYSTAL_CONFIGS
        
    Returns:
        Dictionary with crystal configuration
    """
    if crystal_type not in CRYSTAL_CONFIGS:
        print(f"Warning: Unknown crystal type '{crystal_type}', using '5MHz_standard'")
        crystal_type = '5MHz_standard'
        
    return CRYSTAL_CONFIGS[crystal_type].copy()


def get_application_preset(application='biosensing'):
    """
    Get configuration preset for specific application
    
    Args:
        application: Key from APPLICATION_PRESETS
        
    Returns:
        Dictionary with application-specific settings
    """
    if application not in APPLICATION_PRESETS:
        print(f"Warning: Unknown application '{application}', using 'biosensing'")
        application = 'biosensing'
        
    preset = APPLICATION_PRESETS[application].copy()
    
    # Include the referenced crystal configuration
    crystal_config = get_crystal_config(preset['crystal_config'])
    preset['crystal_params'] = crystal_config
    
    return preset


def apply_troubleshooting_preset(base_config, issue='weak_signal'):
    """
    Apply troubleshooting modifications to base configuration
    
    Args:
        base_config: Base crystal configuration
        issue: Key from TROUBLESHOOTING
        
    Returns:
        Modified configuration
    """
    if issue not in TROUBLESHOOTING:
        print(f"Warning: Unknown issue '{issue}', no modifications applied")
        return base_config
        
    config = base_config.copy()
    fixes = TROUBLESHOOTING[issue]
    
    # Apply modifications
    if 'search_range_multiplier' in fixes:
        config['search_range'] = int(config['search_range'] * fixes['search_range_multiplier'])
        
    if 'search_step_divisor' in fixes:
        config['search_step'] = max(1, config['search_step'] // fixes['search_step_divisor'])
        
    print(f"Applied troubleshooting preset: {fixes['description']}")
    return config


def print_available_configurations():
    """
    Print all available configurations for reference
    """
    print("=== Available Crystal Configurations ===")
    for name, config in CRYSTAL_CONFIGS.items():
        freq_mhz = config['center_freq'] / 1e6
        print(f"{name:20s}: {freq_mhz:.0f} MHz, ±{config['search_range']/1000:.0f}kHz search, {config['fine_step']}Hz fine step")
    
    print("\n=== Available Application Presets ===")
    for name, preset in APPLICATION_PRESETS.items():
        print(f"{name:20s}: {preset['description']}")
    
    print("\n=== Available Troubleshooting Presets ===")
    for name, fix in TROUBLESHOOTING.items():
        print(f"{name:20s}: {fix['description']}")


if __name__ == "__main__":
    # Print available configurations
    print_available_configurations()
    
    # Example usage
    print("\n=== Example Configuration Usage ===")
    
    # Get biosensing configuration
    biosensing_config = get_application_preset('biosensing')
    print(f"Biosensing crystal frequency: {biosensing_config['crystal_params']['center_freq']/1e6:.1f} MHz")
    
    # Apply troubleshooting for weak signal
    weak_signal_config = apply_troubleshooting_preset(
        biosensing_config['crystal_params'], 
        'weak_signal'
    )
    print(f"Modified search range: ±{weak_signal_config['search_range']/1000:.0f} kHz")
