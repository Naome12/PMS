import serial
import time
from datetime import datetime
from db_utils import get_db_connection, update_payment_status

# === CONFIG ===

SERIAL_PORT = 'COM6'  # Change to your port
BAUD_RATE = 9600
RATE_PER_HOUR = 500


def find_latest_unpaid(plate):
    """Find the latest unpaid entry for a plate number"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, plate_number, entry_time 
                FROM plates 
                WHERE plate_number = %s 
                AND payment_status = 0 
                ORDER BY entry_time DESC 
                LIMIT 1
                """,
                (plate,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    'id': result[0],
                    'plate_number': result[1],
                    'entry_time': result[2]
                }
            return None
        except Exception as e:
            print(f"Error finding latest unpaid entry: {e}")
            return None
        finally:
            if conn:
                conn.close()


def mark_as_paid(entry, paid_amount):
    """Mark an entry as paid in the database"""
    if update_payment_status(entry['plate_number'], paid_amount):
        print(f"Marked {entry['plate_number']} as paid with amount {paid_amount} RWF")
        return True
    return False


def clean_plate(plate_raw):
    return plate_raw.replace('\x00', '').strip().upper()


def main():
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=10)
    print(f"Listening on {SERIAL_PORT}...")

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()

            if not line or line == ",-1":
                continue

            print(f"Received: {line}")
            parts = [part.strip() for part in line.split(',')]
            if len(parts) != 2:
                print("Invalid format.")
                continue

            plate_raw, balance_str = parts
            plate = clean_plate(plate_raw)

            try:
                balance = int(balance_str)
            except ValueError:
                print("Invalid balance received.")
                continue

            entry = find_latest_unpaid(plate)
            if not entry:
                print(f"No unpaid entry for {plate}")
                ser.write(b'0\n')
                continue

            entry_time = entry['entry_time']
            now = datetime.now()
            duration = round((now - entry_time).total_seconds() / 3600, 3) # Duration in hours, rounded to 3 decimal places

            # Calculate due amount based on exact duration
            due = int(duration * RATE_PER_HOUR)

            print(f"Due for {plate}: {due} RWF")

            # Insufficient balance handling with top-up
            while balance < due:
                print(f"Insufficient balance: {balance} < {due}")
                ser.write(b'-1\n')  # Signal insufficient balance to Arduino

                # Wait for Arduino's "insufficient" confirmation
                start_time = time.time()
                confirmation = None
                while True:
                    if ser.in_waiting:
                        response = ser.readline().decode().strip()
                        if response == "insufficient":
                            confirmation = "insufficient"
                            break
                    if time.time() - start_time > 5:
                        print("No response from Arduino.")
                        break

                if confirmation != "insufficient":
                    break  # Exit loop if no confirmation

                # Prompt user for top-up
                choice = input("Would you like to top-up? (yes/no): ").strip().lower()
                if choice != 'yes':
                    print("Payment aborted.")
                    break

                # Get valid top-up amount
                while True:
                    try:
                        topup = int(input("Enter top-up amount (positive integer): "))
                        if topup > 0:
                            break
                        print("Amount must be positive.")
                    except ValueError:
                        print("Invalid input. Enter a number.")

                # Send top-up command to Arduino
                ser.write(f"topup,{topup}\n".encode())
                print(f"Sent top-up: {topup}")

                # Wait for new balance confirmation
                start_time = time.time()
                topped = False
                while True:
                    if ser.in_waiting:
                        response = ser.readline().decode().strip()
                        if response.startswith("topped,"):
                            try:
                                new_balance = int(response.split(',')[1])
                                balance = new_balance
                                print(f"New balance: {balance} RWF")
                                topped = True
                                break
                            except:
                                print("Error processing top-up.")
                                break
                    if time.time() - start_time > 5:
                        print("Top-up timeout.")
                        break

                if not topped:
                    continue  # Retry top-up

                # Recalculate due with updated time
                now = datetime.now()
                duration = round((now - entry_time).total_seconds() / 3600, 3) # Duration in hours, rounded to 3 decimal places

                # Recalculate due amount based on exact duration
                due = int(duration * RATE_PER_HOUR)
                print(f"Updated due: {due} RWF")

            if balance >= due:
                # Proceed with payment
                ser.write(f"{due}\n".encode())
                start_time = time.time()
                while True:
                    if ser.in_waiting:
                        response = ser.readline().decode().strip()
                        if response == "done":
                            print("Payment successful!")
                            # Pass the calculated 'due' amount when marking as paid
                            mark_as_paid(entry, due)
                            break
                        elif response == "insufficient":
                            print("Unexpected insufficient balance after top-up.")
                            break
                    if time.time() - start_time > 5:
                        print("Confirmation timeout.")
                        break

        except KeyboardInterrupt:
            print("Exiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    ser.close()


if __name__ == "__main__":
    main()