"""
    acquisition.py
    use serial to acquire data from LOSTwheel
"""

import sys
import serial
import time

def main(argv):

    # some params
    port = 'COM3'
    baudrate = 9600

    # create serial communication
    arduino = serial.Serial(port=port, baudrate=baudrate)

    # start recording
    for i in range(100):
        print(arduino.readline())
        

    arduino.close()


if __name__ == '__main__':
    main(sys.argv)
