import time
import pyvisa

rm = pyvisa.ResourceManager()

# Open the instrument (replace with your actual resource string or rm.list_resources()[0])
psu = rm.open_resource('USB0::0x1AB1::0x0E11::DP8E214600333::INSTR')

# Ensure Channel 1 output is enabled
psu.write(':OUTP CH1,ON')

# Loop 10 times to measure voltage, current, and power
for i in range(1000):
    # Query all three values at once for Channel 1
    raw_data = psu.query(':MEAS:ALL? CH1')

    # Split the comma-separated string and convert each value to a float
    voltage, current, power = [float(val) for val in raw_data.strip().split(',')]

    print(f"Reading {i + 1}: {voltage:.4f} V | {current:.4f} A | {power:.4f} W")

    # Wait 1 second before the next reading
    time.sleep(.1)

psu.close()