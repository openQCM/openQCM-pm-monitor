# Flow and Particulate Concentration Calculation — QCM Impactor System

## System architecture

The system measures atmospheric particulate concentration using a QCM (Quartz Crystal Microbalance) as an inertial impactor.

**Pneumatic chain:**

ambient air → impactor nozzle → quartz surface → exhaust duct → FS3000 sensor → outlet hole

The FS3000 velocity sensor is mounted in the exhaust duct, downstream of the quartz. The duct cross-section at the measurement point coincides with the outlet hole.

## Measurement cycle

1. **Sampling:** the pump draws air through the nozzle; particles impact on the quartz by inertia.
2. **Flow interruption:** the pump stops, eliminating pressure and mechanical-stress effects on the crystal.
3. **Δf reading:** the change in the quartz resonance frequency is measured.
4. **Calculation:** deposited mass and concentration are derived from the frequency shift.

## Velocity sensor — FS3000

- Type: thermopile MEMS, 12-bit I²C digital output
- Available versions: FS3000-1005 (0–7.23 m/s), FS3000-1015 (0–15 m/s)
- Accuracy: ±5 % of full scale
- Response time: 125 ms (max sample rate ~8 Hz)
- Non-linear transfer curve (counts → m/s): interpolate the datasheet table or fit with a polynomial
- The sensor measures *point* velocity, not the average velocity over the cross-section

## Volumetric flow rate

### Mode 1 — Analytical (debug / testing)

Flow rate = measured velocity × outlet cross-section area:

```
Q = v_sensor · π · D² / 4
```

- `D` = outlet hole diameter (configurable parameter)
- `v_sensor` = FS3000 reading (m/s)
- `Q` = volumetric flow rate (m³/s)

**Limitations:** the value is approximate because the sensor measures point velocity (typically near the centre of the flow) rather than the section average. The velocity profile inside the duct is not uniform.

### Mode 2 — Calibrated (operational measurements)

Flow rate = measured velocity × empirical calibration factor obtained against a reference flowmeter:

```
Q = K_cal · v_sensor
```

- `K_cal` = calibration factor (configurable parameter, units: m²)
- Absorbs all non-idealities: velocity profile, geometry, sensor placement

**Calibration procedure:** connect a certified flowmeter, acquire (v_sensor, Q_reference) pairs at 8–10 points across the operating range, verify linearity. If the relation is non-linear, replace the single `K_cal` with a polynomial fit or a lookup table.

## Sampled volume

```
V = Q · t_pump
```

- `t_pump` = effective pump-on time (s), excluding start/stop ramps
- If the flow is unsteady, integrate: `V = ∫ Q(t) dt`

## Concentration

```
C = Δm / V
```

- `Δm` = mass change on the quartz (µg), derived from the frequency shift via the Sauerbrey relation
- `V` = sampled volume (m³)
- `C` = particulate concentration (µg/m³)

## Operational notes

- Verify that the velocity in the exhaust duct lies within the FS3000 useful range; at low velocities the relative error becomes unacceptable.
- The FS3000 can also be used as a flow-stability monitor: if its reading drifts beyond a threshold during a cycle, the measurement should be invalidated.
- For regulatory compliance, the sampled volume should be reported at standard conditions (25 °C, 1 atm — or 0 °C, 1 atm — depending on the applicable standard).
