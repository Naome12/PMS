import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
from collections import Counter
import platform
import sys
from db_utils import init_db, log_plate_entry, is_vehicle_inside

# Initialize database
init_db()

# ===== CONFIG =====
model = YOLO('best.pt')  # Load YOLOv8 model
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)

# ===== Serial Port Detection =====
def detect_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    system = platform.system()
    for port in ports:
        if system == "Linux" and ("ttyUSB" in port.device or "ttyACM" in port.device):
            return port.device
        elif system == "Darwin" and ("usbmodem" in port.device or "usbserial" in port.device):
            return port.device
        elif system == "Windows" and "COM" in port.device:
            return port.device
    return None

arduino_port = detect_arduino_port()
if arduino_port:
    print(f"[CONNECTED] Arduino on {arduino_port}")
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    time.sleep(2)
else:
    print("[ERROR] Arduino not detected.")
    arduino = None

# ===== Read Distance from Arduino =====
def read_distance(arduino):
    if arduino and arduino.in_waiting > 0:
        try:
            line = arduino.readline().decode('utf-8').strip()
            return float(line)
        except ValueError:
            return None
    return None

# ===== Webcam & Plate Detection =====
cap = cv2.VideoCapture(0)
plate_buffer = []
entry_cooldown = 300  # seconds (5 mins)
last_saved_plate = None
last_entry_time = 0

print("[SYSTEM] Ready. Press 'q' to exit.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    distance = read_distance(arduino)
    if distance is None:
        continue
    print(f"[SENSOR] Distance: {distance} cm")

    if distance <= 50:
        results = model(frame)

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = frame[y1:y2, x1:x2]

                gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                plate_text = pytesseract.image_to_string(
                    thresh,
                    config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                ).strip().replace(" ", "")

                if "RA" in plate_text:
                    start_idx = plate_text.find("RA")
                    plate_candidate = plate_text[start_idx:]
                    if len(plate_candidate) >= 7:
                        plate_candidate = plate_candidate[:7]
                        prefix, digits, suffix = plate_candidate[:3], plate_candidate[3:6], plate_candidate[6]
                        if prefix.isalpha() and digits.isdigit() and suffix.isalpha():
                            print(f"[VALID] Plate Detected: {plate_candidate}")
                            plate_buffer.append(plate_candidate)

                            if len(plate_buffer) >= 3:
                                most_common = Counter(plate_buffer).most_common(1)[0][0]
                                current_time = time.time()

                                # === MAIN VALIDATION ===
                                if is_vehicle_inside(most_common):
                                    print(f"[TERMINATED] Plate {most_common} is already inside. Exiting system...")
                                    cap.release()
                                    if arduino:
                                        arduino.close()
                                    cv2.destroyAllWindows()
                                    sys.exit()

                                # Allow entry if cooldown passed or different plate
                                if (most_common != last_saved_plate or
                                        (current_time - last_entry_time) > entry_cooldown):

                                    if log_plate_entry(most_common):
                                        print(f"[SAVED] {most_common} logged to database.")

                                        if arduino:
                                            arduino.write(b'1')
                                            print("[GATE] Opening gate (sent '1')")
                                            time.sleep(15)
                                            arduino.write(b'0')
                                            print("[GATE] Closing gate (sent '0')")

                                        last_saved_plate = most_common
                                        last_entry_time = current_time
                                    else:
                                        print("[ERROR] Failed to log plate to database.")
                                else:
                                    print("[SKIPPED] Duplicate within 5 min window.")

                                plate_buffer.clear()

                cv2.imshow("Plate", plate_img)
                cv2.imshow("Processed", thresh)
                time.sleep(0.5)

    annotated_frame = results[0].plot() if distance <= 50 else frame
    cv2.imshow('Webcam Feed', annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ===== Cleanup =====
cap.release()
if arduino:
    arduino.close()
cv2.destroyAllWindows()
