#!/usr/bin/env python3
"""
openQCM NEXT Enhanced Sweep Controller with Dynamic Tracking
==========================================================

Enhanced version with three key improvements:
1. Dynamic resonance frequency tracking (instead of fixed initial frequency)
2. Peak detection on every sweep (adaptive tracking)  
3. Optional sliding window for monitoring (configurable)

DISSIPATION CALCULATION:
- Formula: D = Δf₋₃dB / f₀
- Where f_max and f_min are frequencies at -3dB threshold points
- f0 is the resonance frequency at peak amplitude

Version: 2.1.0 (Simplified peak detection + f0 alignment)
Date: 2025-01-20
"""

import serial
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks, savgol_filter
from scipy.interpolate import UnivariateSpline
from typing import Tuple, List, Optional, Dict, Deque
import time
import logging
import os
import json
from collections import deque

from openqcm.constants import SG_WINDOW_SIZE, SG_ORDER, SPLINE_FACTOR
from openqcm.paths import app_data_dir


# ===== AD8302 CONVERSION CONSTANTS =====
VMAX = 3.3          # ADC reference voltage
BITMAX = 4096       # 12-bit ADC resolution
ADC_TO_VOLT = VMAX / BITMAX
VCP = 0.9           # AD8302 comparator offset voltage
GAIN_SLOPE = 0.03   # V/dB
PHASE_SLOPE = 0.01  # V/degree

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration file for storing resonance frequency.
# Lives next to the executable (frozen) or in <project>/data/ (dev) so the
# value survives across runs even when the package is read-only (PyInstaller
# --onefile extracts to a temp dir wiped on exit).
CONFIG_FILE = os.path.join(app_data_dir(), 'resonance_config.json')

class OpenQCMSweepEnhanced:
    """
    OpenQCM NEXT Enhanced Sweep Controller with Dynamic Tracking
    
    Key Features:
    - Dynamic resonance tracking (updates on each sweep)
    - Sliding window for monitoring applications
    - Simplified peak detection using maximum amplitude
    - Dissipation formula: D = Δf₋₃dB / f₀
    """
    
    def __init__(self, port: str = '/dev/ttyACM0', baudrate: int = 115200, timeout: float = 5.0):
        """Initialize the enhanced OpenQCM sweep controller"""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None
        
        # Dynamic tracking variables
        self.initial_resonance_freq = None  # Initial frequency (for reference)
        self.current_resonance_freq = None  # Current tracked frequency
        self.last_sweep_data = None
        self.last_qcm_parameters = None
        self._last_processed = None  # Last SG+spline processed signal
        # Metadata from sweep output (temperature, TEC status, flow, pump)
        self.last_sweep_metadata = None
        
        # Peak tracking history for stability analysis
        self.resonance_history = deque(maxlen=50)
        
        # Default sweep parameters
        self.default_search_range = 50000  # ±50kHz for initial peak search
        self.default_search_step = 100     # 100Hz steps for peak search
        self.default_fine_step = 10        # 10Hz steps for fine sweep
        
        # Tracking parameters

        
        # Load saved resonance configuration if available
        self.load_resonance_config()

    def _adc_to_gain(self, adc_value: float) -> float:
        """
        Convert ADC reading to gain in dB
        
        Args:
            adc_value: Raw ADC count (0-4095)
            
        Returns:
            Gain in dB
        """
        volt = adc_value * ADC_TO_VOLT / 2.0
        gain_dB = (volt - VCP) / GAIN_SLOPE
        return gain_dB

    def _adc_to_phase(self, adc_value: float) -> float:
        """
        Convert ADC reading to phase in degrees
        
        Args:
            adc_value: Raw ADC count (0-4095)
            
        Returns:
            Phase in degrees
        """
        volt = adc_value * ADC_TO_VOLT / 1.5
        phase_deg = (volt - VCP) / PHASE_SLOPE
        return phase_deg
        
    def connect(self) -> bool:
        """Establish serial connection to openQCM device"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            
            time.sleep(2)
            
            self.serial_connection.write(b'F\n')
            response = self.serial_connection.readline().decode().strip()
            
            if response:
                logger.info(f"Connected to openQCM - Firmware: {response}")
                return True
            else:
                logger.error("No response from openQCM device")
                return False
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            logger.info("Disconnected from openQCM")
    
    def send_sweep_command(self, freq_start: int, freq_stop: int, freq_step: int) -> List[Tuple[float, float]]:
        """
        Send frequency sweep command and collect data.

        Uses a bulk-read pattern: instead of one ``readline()`` per data point
        (which is one syscall each — costly under USB pass-through on a VM),
        we drain whatever bytes are already in the kernel buffer with a single
        ``read(in_waiting)`` per loop iteration. The firmware terminates the
        sweep with a metadata line ending in ``s`` — we keep accumulating into
        a string buffer until that trailer appears, then parse the whole
        buffer in memory (no further I/O).

        Reduces ~10000 syscalls per Fine sweep down to ~10–20.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Serial connection not established")

        self.serial_connection.flushInput()
        command = f"{freq_start};{freq_stop};{freq_step}\n"
        logger.debug(f"Sending sweep command: {command.strip()}")
        self.serial_connection.write(command.encode())

        # ── Bulk read with trailer-based framing ──
        buffer = ''
        deadline = time.time() + 5.0   # absolute timeout safety net
        trailer_seen = False
        while time.time() < deadline:
            n_avail = self.serial_connection.in_waiting
            if n_avail:
                try:
                    buffer += self.serial_connection.read(n_avail).decode('utf-8', errors='ignore')
                except OSError:
                    pass
                # Trailer is a metadata line that ends with 's' followed by newline,
                # or the very last char if firmware did not send a trailing newline.
                if 's\n' in buffer or buffer.rstrip().endswith('s'):
                    trailer_seen = True
                    break
            else:
                time.sleep(0.001)

        if not trailer_seen:
            logger.warning(f"Sweep timeout: collected {len(buffer)} bytes, no trailer received")

        # ── Parse buffer in memory (no more I/O) ──
        sweep_data = []
        self.last_sweep_metadata = None
        for line in buffer.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Metadata line ends with 's' (e.g. "T;status;error;flow;pump;s")
            if line.endswith('s'):
                self.last_sweep_metadata = self._parse_sweep_final_line(line)
                break
            if ';' in line:
                parts = line.split(';')
                if len(parts) >= 2:
                    try:
                        adc_amp = float(parts[0])
                        adc_phase = float(parts[1])
                        sweep_data.append((
                            self._adc_to_gain(adc_amp),
                            self._adc_to_phase(adc_phase)
                        ))
                    except ValueError:
                        continue

        return sweep_data

    def _parse_sweep_final_line(self, line: str) -> dict:
        """
        Parse the final line of sweep output containing metadata.
        Format from firmware: temperature;tec_status;tec_error;flow;pump_speed;s
        Example: 25.123;2;0;1.234;150;s
        """
        metadata = {'valid': False}
        
        try:
            clean = line.rstrip('s').rstrip(';')
            parts = clean.split(';')
            
            if len(parts) >= 5:
                metadata['temperature'] = float(parts[0])
                metadata['tec_status'] = int(parts[1])
                metadata['tec_error'] = int(parts[2])
                metadata['flow'] = float(parts[3])
                metadata['pump_speed'] = int(parts[4])
                metadata['valid'] = True
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse metadata from '{line}': {e}")
        
        return metadata

    def get_last_sweep_metadata(self) -> dict:
        """Get metadata from the last sweep (temperature, TEC, flow, pump)"""
        return self.last_sweep_metadata.copy() if self.last_sweep_metadata else {}
    
    # =========================================================================
    # SIGNAL PROCESSING PIPELINE (from openQCM Next)
    # =========================================================================

    def process_sweep_signal(self, frequencies: np.ndarray, amplitudes: np.ndarray) -> Dict:
        """
        Process raw sweep data: Savitzky-Golay filter + UnivariateSpline.

        Pipeline (from openQCM Next Serial.py):
        1. Savitzky-Golay smoothing (removes high-freq noise, preserves peak)
        2. UnivariateSpline fitting (additional smoothing, same N points — no upsampling)

        Args:
            frequencies: Raw sweep frequencies (Hz)
            amplitudes: Raw sweep amplitudes (dB)

        Returns:
            Dict with 'frequencies_filtered', 'amplitudes_filtered'
        """
        n_points = len(amplitudes)

        # Adaptive SG window: must be odd and < n_points
        sg_window = min(SG_WINDOW_SIZE, n_points)
        if sg_window % 2 == 0:
            sg_window -= 1
        if sg_window < SG_ORDER + 2:
            sg_window = SG_ORDER + 2
            if sg_window % 2 == 0:
                sg_window += 1

        # Step 1: Savitzky-Golay filter
        filtered_mag = savgol_filter(amplitudes, sg_window, SG_ORDER)

        # Step 2: UnivariateSpline on SG-filtered data, evaluated at same N points
        try:
            x_range = np.arange(n_points)
            spline = UnivariateSpline(x_range, filtered_mag, s=SPLINE_FACTOR)
            filtered_mag = spline(x_range)
        except Exception as e:
            logger.warning(f"Spline fitting failed, using SG only: {e}")

        logger.debug(f"Signal processing: {n_points} pts, SG window={sg_window}, spline s={SPLINE_FACTOR}")

        return {
            'frequencies_filtered': frequencies,
            'amplitudes_filtered': filtered_mag,
        }

    # =========================================================================
    # VER 2.1.0: SIMPLIFIED PEAK DETECTION - Uses only maximum amplitude
    # =========================================================================

    def find_current_resonance_peak(self, frequencies: np.ndarray, amplitudes: np.ndarray,
                                   phases: np.ndarray = None) -> Optional[int]:
        """
        Find current resonance peak using maximum amplitude on processed signal.

        Uses SG-filtered + spline-interpolated data for robust peak detection.

        Args:
            frequencies: Array of sweep frequencies (Hz)
            amplitudes: Array of amplitude values (dB)
            phases: Array of phase values (degrees) - not used

        Returns:
            Resonance frequency (Hz) at maximum amplitude, or None if invalid
        """
        try:
            if len(amplitudes) == 0:
                logger.warning("Empty amplitude array")
                return None

            # Process signal through Savitzky-Golay filter
            processed = self.process_sweep_signal(frequencies, amplitudes)
            freq_filt = processed['frequencies_filtered']
            amp_filt = processed['amplitudes_filtered']

            # Store processed data for later use (dissipation, plots)
            self._last_processed = processed

            # Peak detection on filtered signal
            peak_idx = np.argmax(amp_filt)
            current_peak = int(freq_filt[peak_idx])

            logger.debug(f"Peak found at index {peak_idx}: {current_peak/1e6:.6f} MHz "
                        f"(amplitude: {amp_filt[peak_idx]:.2f} dB)")
            
            # Update tracking
            self.resonance_history.append(current_peak)
            self.current_resonance_freq = current_peak
            return current_peak
            
        except Exception as e:
            logger.error(f"Current resonance tracking failed: {e}")
            return self.current_resonance_freq
    
    # =========================================================================
    # MAIN SWEEP METHOD WITH TRACKING
    # =========================================================================
    
    def sweep_around_resonance_with_tracking(self, sweep_range: int, step_size: int, 
                                           resonance_freq: Optional[int] = None,
                                           use_dynamic_tracking: bool = True) -> Dict:
        """
        Perform frequency sweep with dynamic peak tracking.
        
        VER 2.1.0: Now ensures current_resonance_freq is always aligned with f0.
        
        Args:
            sweep_range: Range around resonance (±Hz)
            step_size: Step size in Hz
            resonance_freq: Starting resonance frequency (uses current if None)
            use_dynamic_tracking: Whether to update resonance frequency during sweep
        """
        # Use current resonance or provided frequency
        if resonance_freq is None:
            if self.current_resonance_freq:
                resonance_freq = self.current_resonance_freq
            elif self.initial_resonance_freq:
                resonance_freq = self.initial_resonance_freq
                self.current_resonance_freq = resonance_freq
            else:
                raise ValueError("No resonance frequency available. Run find_resonance_peak() first.")
        
        freq_start = int(resonance_freq - sweep_range)
        freq_stop = int(resonance_freq + sweep_range)
        step_size = int(step_size)

        logger.debug(f"Sweep around {resonance_freq/1e6:.6f} MHz "
                    f"(±{sweep_range/1000:.1f} kHz, {step_size} Hz steps)")

        # Perform sweep
        sweep_data = self.send_sweep_command(freq_start, freq_stop, step_size)
        
        if not sweep_data:
            logger.error("No data collected for sweep")
            return {}
            
        frequencies = np.arange(freq_start, freq_start + len(sweep_data) * step_size, step_size)
        amplitudes = np.array([point[0] for point in sweep_data])
        phases = np.array([point[1] for point in sweep_data])
        
        # VER 2.1.0: Dynamic peak tracking using simplified method
        if use_dynamic_tracking:
            current_peak = self.find_current_resonance_peak(frequencies, amplitudes, phases)
            if current_peak:
                resonance_freq = current_peak
                logger.debug(f"Resonance updated: {resonance_freq/1e6:.6f} MHz")
        
        # Include processed (interpolated) data in results for GUI plotting
        processed = getattr(self, '_last_processed', None)

        results = {
            'initial_resonance_freq': self.initial_resonance_freq,
            'current_resonance_freq': self.current_resonance_freq,
            'resonance_freq': resonance_freq,  # For backward compatibility
            'frequencies': frequencies,
            'amplitudes': amplitudes,
            'phases': phases,
            'sweep_range': sweep_range,
            'step_size': step_size,
            'num_points': len(sweep_data),
            'timestamp': time.time(),
            'tracking_enabled': use_dynamic_tracking
        }

        # Add SG-filtered signal data for GUI visualization and dissipation calc
        if processed:
            results['amplitudes_filtered'] = processed['amplitudes_filtered']
        
        # Calculate QCM parameters with dissipation
        qcm_params = self.calculate_comprehensive_qcm_parameters(results)
        results.update(qcm_params)

        # =====================================================================
        # VER 2.1.0 FIX #2: Align resonance_freq and current_resonance_freq with f0
        # =====================================================================
        if 'f0' in qcm_params:
            results['resonance_freq'] = qcm_params['f0']
            results['current_resonance_freq'] = qcm_params['f0']
            self.current_resonance_freq = qcm_params['f0']
            logger.debug(f"Aligned current_resonance_freq with f0: {qcm_params['f0']/1e6:.6f} MHz")
        
        self.last_sweep_data = results
        
        # Log tracking information
        if self.resonance_history:
            freq_drift = self.current_resonance_freq - self.initial_resonance_freq if self.initial_resonance_freq else 0
            stability = np.std(list(self.resonance_history)[-10:]) if len(self.resonance_history) > 1 else 0
            
            logger.debug(f"Tracking stats - Drift: {freq_drift:+.1f} Hz, Stability: {stability:.1f} Hz")
        
        return results
    
    def calculate_comprehensive_qcm_parameters(self, data: Dict) -> Dict:
        """
        Calculate QCM parameters from sweep data.
        Dissipation formula: D = Δf₋₃dB / f₀

        Uses filtered signal (SG + spline) when available for more
        accurate -3dB bandwidth calculation.
        """
        if not data or 'amplitudes' not in data:
            return {}

        # Use SG-filtered signal for dissipation if available
        if 'amplitudes_filtered' in data and len(data['amplitudes_filtered']) > 0:
            frequencies = data['frequencies']
            amplitudes = data['amplitudes_filtered']
        else:
            frequencies = data['frequencies']
            amplitudes = data['amplitudes']

        resonance_freq = data.get('current_resonance_freq') or data.get('resonance_freq')

        if not resonance_freq:
            return {}

        # Calculate dissipation using half-power (-3dB) method
        dissipation_params = self._calculate_dissipation_halfpower(
            frequencies, amplitudes, resonance_freq
        )

        params = dissipation_params.copy()

        # Add tracking information
        if self.resonance_history:
            params['frequency_stability'] = np.std(list(self.resonance_history)[-10:])
            params['frequency_drift_rate'] = self._calculate_drift_rate()

        # Map values for GUI compatibility
        if 'q_factor' in params:
            params['q_factor_3sigma'] = params['q_factor']
        if 'dissipation' in params:
            params['dissipation_3sigma'] = params['dissipation']

        self.last_qcm_parameters = params

        return params

    def _calculate_dissipation_halfpower(self, frequencies: np.ndarray, amplitudes: np.ndarray,
                                         resonance_freq: int) -> Dict:
        """
        Calculate dissipation using Half-Power (-3dB) method.

        Formulas:
        - Q-factor = f₀ / Δf₋₃dB
        - Dissipation = Δf₋₃dB / f₀ = 1/Q

        Args:
            frequencies: Array of frequencies [Hz]
            amplitudes: Array of gain [dB]
            resonance_freq: Resonance frequency [Hz]

        Returns:
            Dict with dissipation, Q-factor, bandwidth, f_min, f_max
        """
        try:
            # 1. Find peak (maximum amplitude)
            peak_idx = np.argmax(amplitudes)
            peak_value = amplitudes[peak_idx]
            f0 = frequencies[peak_idx]
            
            # 2. Calculate -3dB threshold from peak
            halfpower_threshold = peak_value - 3.0  # -3dB from peak
            
            logger.debug(f"Peak: {peak_value:.2f} dB at {f0/1e6:.6f} MHz, "
                        f"Threshold -3dB: {halfpower_threshold:.2f} dB")
            
            # 3. Find crossing points
            # LEFT side (before peak)
            left_mask = amplitudes[:peak_idx] < halfpower_threshold
            left_indices = np.where(left_mask)[0]
            
            if len(left_indices) > 0:
                left_cross_idx = left_indices[-1]  # Last point below threshold
                # Linear interpolation for precision
                if left_cross_idx < peak_idx - 1:
                    f_min = self._interpolate_crossing(
                        frequencies[left_cross_idx], frequencies[left_cross_idx + 1],
                        amplitudes[left_cross_idx], amplitudes[left_cross_idx + 1],
                        halfpower_threshold
                    )
                else:
                    f_min = frequencies[left_cross_idx]
            else:
                f_min = frequencies[0]
                logger.warning("Left crossing not found, using sweep edge")
            
            # RIGHT side (after peak)
            right_mask = amplitudes[peak_idx:] < halfpower_threshold
            right_indices = np.where(right_mask)[0]
            
            if len(right_indices) > 0:
                right_cross_idx = peak_idx + right_indices[0]  # First point below threshold
                if right_cross_idx > peak_idx + 1 and right_cross_idx < len(frequencies) - 1:
                    f_max = self._interpolate_crossing(
                        frequencies[right_cross_idx - 1], frequencies[right_cross_idx],
                        amplitudes[right_cross_idx - 1], amplitudes[right_cross_idx],
                        halfpower_threshold
                    )
                else:
                    f_max = frequencies[right_cross_idx]
            else:
                f_max = frequencies[-1]
                logger.warning("Right crossing not found, using sweep edge")
            
            # 4. Calculate bandwidth
            bandwidth = f_max - f_min
            
            if bandwidth <= 0:
                logger.error("Negative or zero bandwidth!")
                return self._fallback_dissipation(resonance_freq)
            
            # 5. Calculate Q-factor and Dissipation (CORRECT FORMULAS)
            q_factor = f0 / bandwidth
            dissipation = bandwidth / f0  # D = 1/Q
            
            # Physical validation
            if dissipation > 1e-2:
                logger.warning(f"Very high dissipation: {dissipation:.2e}")
            if dissipation < 1e-8:
                logger.warning(f"Very low dissipation: {dissipation:.2e}")
            
            logger.debug(f"-3dB method: f₀={f0/1e6:.6f} MHz, Δf={bandwidth:.1f} Hz, "
                        f"Q={q_factor:.0f}, D={dissipation:.2e}")
            
            return {
                'dissipation': dissipation,
                'q_factor': q_factor,
                'bandwidth': bandwidth,
                'f_min': f_min,
                'f_max': f_max,
                'f0': f0,
                'peak_gain_dB': peak_value,
                'halfpower_threshold_dB': halfpower_threshold,
                'calculation_method': 'halfpower_minus3dB',
                'formula': 'D = Δf₋₃dB / f₀'
            }
            
        except Exception as e:
            logger.error(f"-3dB dissipation calculation failed: {e}")
            return self._fallback_dissipation(resonance_freq)

    def _interpolate_crossing(self, f1: float, f2: float, a1: float, a2: float, 
                             threshold: float) -> float:
        """
        Linear interpolation to find precise crossing point.
        
        Args:
            f1, f2: Frequencies of two points
            a1, a2: Amplitudes of two points
            threshold: Threshold value
            
        Returns:
            Interpolated frequency of crossing
        """
        if abs(a2 - a1) < 1e-6:
            return (f1 + f2) / 2
        
        t = (threshold - a1) / (a2 - a1)
        f_cross = f1 + t * (f2 - f1)
        
        return f_cross

    def _fallback_dissipation(self, resonance_freq: int) -> Dict:
        """Fallback values in case of error"""
        return {
            'dissipation': 1e-5,
            'q_factor': 100000,
            'bandwidth': resonance_freq / 100000,
            'f_min': resonance_freq - 50,
            'f_max': resonance_freq + 50,
            'f0': resonance_freq,
            'calculation_method': 'fallback',
            'error': True
        }
    
    def _calculate_drift_rate(self) -> float:
        """Calculate frequency drift rate from tracking history"""
        if len(self.resonance_history) < 3:
            return 0.0
            
        recent_history = list(self.resonance_history)[-20:]
        if len(recent_history) < 3:
            return 0.0
            
        x = np.arange(len(recent_history))
        y = np.array(recent_history)
        
        slope = np.polyfit(x, y, 1)[0]
        return slope
    
    # =========================================================================
    # INITIAL PEAK FINDING (uses advanced methods for robustness)
    # =========================================================================
    
    def find_resonance_peak(self, center_freq: int, search_range: Optional[int] = None,
                          search_step: Optional[int] = None) -> Optional[int]:
        """
        Find initial resonance frequency.

        Pipeline: SG filter + spline on gain and phase, then
        scipy.signal.find_peaks with prominence on gain, cross-check
        with phase derivative for validation.
        """
        if search_range is None:
            search_range = self.default_search_range
        if search_step is None:
            search_step = self.default_search_step

        freq_start = center_freq - search_range
        freq_stop = center_freq + search_range

        logger.info(f"Searching for initial resonance peak around {center_freq} Hz (±{search_range} Hz)")

        sweep_data = self.send_sweep_command(freq_start, freq_stop, search_step)

        if not sweep_data:
            logger.error("No data collected for peak detection")
            return None

        frequencies = np.arange(freq_start, freq_start + len(sweep_data) * search_step, search_step)
        amplitudes = np.array([point[0] for point in sweep_data])
        phases = np.array([point[1] for point in sweep_data])

        # SG filter + spline on gain
        processed = self.process_sweep_signal(frequencies, amplitudes)
        freq_filt = processed['frequencies_filtered']
        amp_filt = processed['amplitudes_filtered']

        # SG filter + spline on phase
        phase_processed = self.process_sweep_signal(frequencies, phases)
        phase_filt = phase_processed['amplitudes_filtered']

        # find_peaks on gain with prominence
        gain_peaks, gain_props = find_peaks(amp_filt, prominence=1.0)

        if len(gain_peaks) == 0:
            # Fallback: argmax (same as monitoring)
            peak_idx = np.argmax(amp_filt)
            print(f"[PEAK] No prominent peaks found, fallback to argmax idx={peak_idx}")
        else:
            # Pick the peak with highest prominence
            best = np.argmax(gain_props['prominences'])
            peak_idx = gain_peaks[best]
            print(f"[PEAK] find_peaks: {len(gain_peaks)} peaks, "
                  f"best prominence={gain_props['prominences'][best]:.2f} dB at idx={peak_idx}")

        resonance_freq = int(freq_filt[peak_idx])

        # Cross-check with phase derivative
        phase_deriv = np.gradient(phase_filt)
        phase_valleys, phase_props = find_peaks(-phase_deriv, prominence=0.1)

        if len(phase_valleys) > 0:
            phase_freqs = freq_filt[phase_valleys]
            distances = np.abs(phase_freqs - resonance_freq)
            closest = phase_valleys[np.argmin(distances)]
            phase_freq = int(freq_filt[closest])
            delta = abs(resonance_freq - phase_freq)
            freq_range = frequencies[-1] - frequencies[0]
            if delta < freq_range * 0.05:
                print(f"[PEAK] Gain-Phase agreement: Δ={delta} Hz (OK)")
            else:
                print(f"[PEAK] Gain-Phase mismatch: gain={resonance_freq} Hz, "
                      f"phase={phase_freq} Hz, Δ={delta} Hz")
        else:
            print(f"[PEAK] No phase valleys found for cross-check")

        # Store result
        self.initial_resonance_freq = resonance_freq
        self.current_resonance_freq = resonance_freq
        self.resonance_history.append(resonance_freq)

        # Peak indices for markers
        gain_peak_idx = peak_idx
        phase_peak_idx = int(np.argmax(phase_filt))

        self.last_sweep_data = {
            'frequencies': frequencies,
            'amplitudes': amplitudes,
            'amplitudes_filtered': amp_filt,
            'phases': phases,
            'phases_filtered': phase_filt,
            'initial_resonance_freq': resonance_freq,
            'current_resonance_freq': resonance_freq,
            'resonance_freq': resonance_freq,
            'gain_peak_freq': float(freq_filt[gain_peak_idx]),
            'gain_peak_amp': float(amp_filt[gain_peak_idx]),
            'phase_peak_freq': float(freq_filt[phase_peak_idx]),
            'phase_peak_val': float(phase_filt[phase_peak_idx]),
        }

        logger.info(f"Initial resonance detected: {resonance_freq/1e6:.6f} MHz")
        self.save_resonance_config()

        return resonance_freq
    
    # (Advanced detection methods removed in v4.3.0 — replaced by
    #  SG+spline+find_peaks pipeline in find_resonance_peak above)
    
    # =========================================================================
    # COMPATIBILITY METHODS
    # =========================================================================
    
    def sweep_around_resonance(self, sweep_range: int, step_size: int, 
                             resonance_freq: Optional[int] = None) -> Dict:
        """Wrapper for backward compatibility"""
        return self.sweep_around_resonance_with_tracking(
            sweep_range, step_size, resonance_freq, use_dynamic_tracking=True
        )
    
    # =========================================================================
    # UTILITY AND CONFIGURATION METHODS
    # =========================================================================
    
    def get_tracking_status(self) -> Dict:
        """Get current tracking status and statistics"""
        status = {
            'initial_frequency': self.initial_resonance_freq,
            'current_frequency': self.current_resonance_freq,
            'tracking_history_length': len(self.resonance_history),
            'dissipation_formula': 'D = Δf₋₃dB / f₀',
            'peak_detection_method': 'maximum_amplitude'
        }
        
        if len(self.resonance_history) > 1:
            status['frequency_drift'] = self.current_resonance_freq - self.initial_resonance_freq
            status['stability_std'] = np.std(list(self.resonance_history)[-10:])
            status['drift_rate'] = self._calculate_drift_rate()
        
        return status
    
    def reset_tracking(self):
        """Reset tracking history and window"""
        self.resonance_history.clear()
        self.current_resonance_freq = self.initial_resonance_freq
        logger.info("Tracking data reset")
    
    def save_resonance_config(self):
        """Save current resonance configuration"""
        if self.initial_resonance_freq is None:
            return
            
        config = {
            'initial_resonance_frequency': self.initial_resonance_freq,
            'current_resonance_frequency': self.current_resonance_freq,
            'timestamp': time.time(),
            'date_saved': time.strftime('%Y-%m-%d %H:%M:%S'),
            'port': self.port,
            'tracking_enabled': True,
            'algorithm_version': 'simplified_max_v2.1.0',
            'dissipation_formula': 'D = Δf₋₃dB / f₀'
        }
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Resonance config saved: {self.current_resonance_freq/1e6:.6f} MHz")
        except Exception as e:
            logger.error(f"Failed to save resonance config: {e}")
    
    def load_resonance_config(self):
        """Load saved resonance configuration"""
        if not os.path.exists(CONFIG_FILE):
            return
            
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                
            self.initial_resonance_freq = config.get('initial_resonance_frequency')
            self.current_resonance_freq = config.get('current_resonance_frequency', self.initial_resonance_freq)
            
            if self.initial_resonance_freq:
                logger.info(f"Loaded resonance config: "
                           f"{self.current_resonance_freq/1e6:.6f} MHz "
                           f"(saved {config.get('date_saved', 'unknown')})")
            
        except Exception as e:
            logger.warning(f"Failed to load resonance config: {e}")
            self.initial_resonance_freq = None
            self.current_resonance_freq = None
    
    def clear_saved_resonance(self):
        """Clear saved resonance configuration"""
        self.initial_resonance_freq = None
        self.current_resonance_freq = None
        self.reset_tracking()
        
        try:
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            logger.info("Resonance config cleared")
        except Exception as e:
            logger.error(f"Failed to clear resonance config: {e}")
    
    # Compatibility properties for GUI integration
    @property
    def resonance_freq(self):
        """Compatibility property - returns current resonance frequency"""
        return self.current_resonance_freq
    
    @resonance_freq.setter
    def resonance_freq(self, value):
        """Compatibility property setter"""
        if self.initial_resonance_freq is None:
            self.initial_resonance_freq = value
        self.current_resonance_freq = value
    
    def get_saved_resonance(self) -> Optional[int]:
        """Get the saved resonance frequency"""
        return self.current_resonance_freq
    
    def get_last_qcm_parameters(self) -> Optional[Dict]:
        """Get the last calculated QCM parameters"""
        return self.last_qcm_parameters
    
    def get_system_status(self) -> Dict:
        """Get complete system status"""
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Serial connection not established")
            
        self.serial_connection.write(b'S?\n')
        time.sleep(0.5)
        
        response = self.serial_connection.readline().decode().strip()
        
        status = {
            'status_response': response,
            'tracking_enabled': True,
            'current_resonance': self.current_resonance_freq,
            'initial_resonance': self.initial_resonance_freq,
            'dissipation_formula': 'D = Δf₋₃dB / f₀',
            'peak_detection': 'maximum_amplitude'
        }
        
        return status


def main():
    """Example usage of the Enhanced OpenQCM sweep controller"""
    print("=" * 70)
    print("openQCM Enhanced Controller v2.1.0")
    print("Simplified peak detection + f0 alignment")
    print("=" * 70)
    
    qcm = OpenQCMSweepEnhanced(port='/dev/ttyACM0')
    
    try:
        if not qcm.connect():
            print("❌ Failed to connect to openQCM device")
            return
            
        print("✅ Connected to openQCM device")
        
        # Find initial resonance
        center_frequency = 10000000  # 10 MHz
        print(f"\n🔍 Searching for initial resonance around {center_frequency/1e6:.1f} MHz...")
        
        resonance_freq = qcm.find_resonance_peak(center_frequency)
        
        if resonance_freq:
            print(f"✅ Initial resonance found at: {resonance_freq/1e6:.6f} MHz")
            
            # Perform monitoring sweep
            print("\n📊 Performing monitoring sweep...")
            
            results = qcm.sweep_around_resonance_with_tracking(
                sweep_range=15000,  # ±15 kHz
                step_size=1,        # 1 Hz steps
                use_dynamic_tracking=True
            )
            
            if results:
                print("\n" + "=" * 50)
                print("QCM MEASUREMENT RESULTS")
                print("=" * 50)
                print(f"f₀ (resonance): {results.get('f0', 0)/1e6:.6f} MHz")
                print(f"current_resonance_freq: {results.get('current_resonance_freq', 0)/1e6:.6f} MHz")
                print(f"Bandwidth: {results.get('bandwidth', 0):.1f} Hz")
                print(f"Q-factor: {results.get('q_factor_3sigma', 0):.0f}")
                print(f"Dissipation: {results.get('dissipation_3sigma', 0):.2e}")
                print(f"Peak detection: maximum_amplitude (simplified)")
            
            print("\n✅ Test complete!")
            
        else:
            print("❌ No resonance peak detected")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        qcm.disconnect()
        print("\n🔌 Disconnected from openQCM")


if __name__ == "__main__":
    main()