import boto3
import pandas as pd
from collections import Counter
from datetime import datetime, date
import json
import io

# Initialize DynamoDB client 
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
response = s3.list_buckets()
print(f"s3 response: {response}")
print(f"s3 connected .............")

# Define table names
appointment_table = 'appointments'
booking_table = 'bookings'
doctor_table = 'doctors'
patient_table = 'patients'


# Custom JSONEncoder to handle datetime.date objects
class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):  # Handle datetime and date objects
            return obj.isoformat()  # Convert to ISO 8601 format (e.g., "2025-01-01") 
        return super().default(obj)
    

# DynamoDB scan or query for appointments and bookings
def get_appointments():
    response = dynamodb.scan(TableName=appointment_table)
    return response['Items']

def get_bookings():
    response = dynamodb.scan(TableName=booking_table)
    return response['Items']

def get_doctors():
    response = dynamodb.scan(TableName=doctor_table)
    return response['Items']

def get_patients():
    response = dynamodb.scan(TableName=patient_table)
    return response['Items']

# Extract data for metrics
def aggregate_metrics():
    appointments = get_appointments()
    bookings = get_bookings()
    doctors = get_doctors()
    patients = get_patients()

    # Prepare data structures for aggregation
    doctor_appointments = {}
    symptom_counter = Counter()
    appointment_frequency = {}

    # Aggregate appointments and bookings
    for booking in bookings:
        try:
            appointment_id = booking['appointment_id']['S']
            diagnosis = booking.get('diagnosis', {}).get('S', 'Unknown')
            patient_id = booking['patient_id']['S']
        except KeyError as e:
            print(f"Error accessing booking data: {e}, booking item: {booking}")
            continue

        # Find the appointment details from the appointments table
        appointment = next((a for a in appointments if a['appointment_id']['S'] == appointment_id), None)
        if not appointment:
            print(f"Appointment ID {appointment_id} not found in appointments table.")
            continue

        doctor_id = appointment['doctor_id']['S']
        appointment_time = appointment['appointment_time']['S']
        appointment_date = datetime.strptime(appointment_time, "%Y-%m-%dT%H:%M:%S.%f").date()

        # Number of appointments per doctor
        if doctor_id not in doctor_appointments:
            doctor_appointments[doctor_id] = 0
        doctor_appointments[doctor_id] += 1

        # Frequency of appointments over time (e.g., daily)
        if appointment_date not in appointment_frequency:
            appointment_frequency[appointment_date] = 0
        appointment_frequency[appointment_date] += 1

        # Common symptoms categorized by specialty
        symptom_counter[diagnosis] += 1

    # Create DataFrame for output
    doctor_data = [{"doctor_id": doctor_id, "appointment_count": count} for doctor_id, count in doctor_appointments.items()]
    specialty_data = [{"diagnosis": diagnosis, "count": count} for diagnosis, count in symptom_counter.items()]
    appointment_frequency_data = [{"date": date, "frequency": frequency} for date, frequency in appointment_frequency.items()]

    # Count patients by gender
    gender_counter = Counter()
    for patient in patients:
        gender = patient.get('gender', {}).get('S', 'Unknown')
        gender_counter[gender] += 1

    # Create DataFrame for gender metrics
    gender_data = [{"gender": gender, "count": count} for gender, count in gender_counter.items()]

    gender_df = pd.DataFrame(gender_data)
    doctor_df = pd.DataFrame(doctor_data)
    symptom_df = pd.DataFrame(specialty_data)
    appointment_frequency_df = pd.DataFrame(appointment_frequency_data)

    # Merge with doctor details to get specialization information
    doctor_df['specialization'] = doctor_df['doctor_id'].apply(lambda doctor_id: next(d['specialization']['S'] for d in doctors if d['doctor_id']['S'] == doctor_id))

    return doctor_df, symptom_df, appointment_frequency_df, gender_df


# Save metrics to CSV and upload to S3
def save_metrics_to_s3():
    try:
        doctor_df, symptom_df, appointment_frequency_df, gender_df = aggregate_metrics()

        # Save doctor metrics to CSV
        doctor_csv = doctor_df.to_csv(index=False)
        symptom_csv = symptom_df.to_csv(index=False)
        appointment_csv = appointment_frequency_df.to_csv(index=False)
        gender_csv = gender_df.to_csv(index=False)

        # Save to S3
        s3.put_object(Bucket='healthsync-data', Key='metrics_data/doctor_metrics.csv', Body=doctor_csv)
        s3.put_object(Bucket='healthsync-data', Key='metrics_data/symptom_metrics.csv', Body=symptom_csv)
        s3.put_object(Bucket='healthsync-data', Key='metrics_data/appointment_metrics.csv', Body=appointment_csv)
        s3.put_object(Bucket='healthsync-data', Key='metrics_data/patient_gender_metrics.csv', Body=gender_csv)
    
        print('save_metrics_to_s3 success')
    
    except Exception as e:
        print(f"Error occurred: {e}")
    

# Run the job
save_metrics_to_s3()
