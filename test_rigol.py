import pyvisa

# Initialize VISA Resource Manager
rm = pyvisa.ResourceManager()

# Search for all connected VISA/USB devices
devices = rm.list_resources()
print("Discovered VISA Devices:", devices)

if devices:
    # Open communication channel with the oscilloscope
    scope = rm.open_resource(devices[0])
    scope.timeout = 5000  # Set a 5-second response timeout

    # Send identification query (*IDN? is the standard SCPI command)
    idn_info = scope.query("*IDN?")
    print("\nConnected Scope Details:")
    print(idn_info)

    # Close connection cleanly
    scope.close()
else:
    print("\nNo VISA devices found! See troubleshooting steps below.")