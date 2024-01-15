import boto3
import argparse
import csv
import os
from datetime import datetime, timedelta
import gspread
import requests
import json
from time import sleep
import subprocess
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets API setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gclient = gspread.authorize(credentials)


parser = argparse.ArgumentParser(description='List non-terminated instances matching a specific tag')
parser.add_argument('--access-key', required=True, help='AWS Access Key')
parser.add_argument('--secret-key', required=True, help='AWS Secret Key')
parser.add_argument('--tag-key', required=True, help='Tag Key to Filter instances')
parser.add_argument('--tag-value', required=True, help='Value for the Tag to filter')
parser.add_argument('--environment', required=True, help='Environment to Run the script')
parser.add_argument('--jira_base_url', help='Jira base URL')
parser.add_argument('--jira_email', help='Jira email')
parser.add_argument('--jira_token', help='Jira API token')

args = parser.parse_args()

aws_access_key = args.access_key
aws_secret_key = args.secret_key
environment = args.environment

# Set the tag key and value to filter instances
tag_key =  args.tag_key
tag_value = args.tag_value

jira_base_url = args.jira_base_url
jira_email = args.jira_email
jira_token = args.jira_token

def create_jira_for_orphaned(jira_base_url, jira_email, jira_token, data):
    issue_url = f"{jira_base_url}issue"
    auth = (jira_email, jira_token) 
    headers = ["InstanceID", "Region", "Type", "State"]
    table_header = "|| " + " || ".join(headers) + " ||"
    table_rows = "\n".join(["| " + " | ".join([item[header] for header in headers]) + " |" for item in data])

    issue_data = {
            "fields": {
            "project":
            {
                "key": "DEVX"
            },
            "summary": "Please delete the Instances (Orphaned pipeline's nodes) (Dev)",
            "description": f"Please delete the following instances:\n{table_header}\n{table_rows}",
            "issuetype": {
                "name": "Support"
            },
             "customfield_10221":{
                "name": "Category (migrated)",
                "value": "SelfService",
            }
        }
    }
    try:
        # Make the API request
        response = requests.post(issue_url, auth=auth, data=json.dumps(issue_data), headers={"Content-Type": "application/json"})
        
        # Check if the request was successful
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            return data['key']
        else:
            print(response.status_code)
            print(response.json())
            return None
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None

# Set the threshold age in days
threshold_age_days = 10

# Set the list of regions to check
regions = ["us-east-1", "eu-central-1", "ap-south-1"]  # Add more regions as needed

# Initialize an empty list to store instance details
instance_details = []

# List of instances that are to be ignored
to_ignore_instances = ["i-0784534dfdc906a5d", "i-0be5988d319de05a8", "i-0848a8fd91ef1d99c", "i-01f82de074b6756a2"]

# Iterate over the specified regions
for region_name in regions:
    ec2 = boto3.client("ec2", region_name=region_name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
    
    # Get instances with the specified tag and filter by termination status
    response = ec2.describe_instances(Filters=[{"Name": f"tag:{tag_key}", "Values": [tag_value]}, {"Name": f"tag-key", "Values": ["Node Pool Id"]},])
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            is_customer_tag_missing = False
            is_age_threshold_reached = False
            is_not_in_narcissus = False
            if instance["InstanceId"] in to_ignore_instances:
                continue
            if instance["State"]["Name"] != "terminated":
                launch_time = instance["LaunchTime"]
                current_time = datetime.now(launch_time.tzinfo)
                age = current_time - launch_time

                
                customer_name = next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Customer Name"), None)
                if customer_name is None:
                    is_customer_tag_missing = True
                
                if age.days >= threshold_age_days:  
                    is_age_threshold_reached = True
                try:
                    customer_name = next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Customer Name"), None)
                    if customer_name is not None:
                        result = subprocess.run(["./narc_cli", "getCustomerDetails", "-c", customer_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                        # if result.returncode == 0:
                        #     continue
                    else:
                        is_not_in_narcissus = True
                        # cannot check because Customer Tag is missing
                except subprocess.CalledProcessError as e:
                    if "Error: 404" in e.stderr:
                        is_not_in_narcissus = True

                if is_customer_tag_missing or is_age_threshold_reached or is_not_in_narcissus:
                    instance_details.append({
                        tag_key: tag_value,
                        "InstanceID": instance["InstanceId"],
                        "Name": next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"), "N/A"),
                        "LaunchTime": launch_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Region": region_name,
                        "Type": instance["InstanceType"],
                        "State": instance["State"]["Name"],
                        "Tags": str(instance["Tags"]),
                        "Can Be Deleted": "Yes",
                        "Customer Tag Missing": ("Yes" if is_customer_tag_missing else "No"),
                        "Exist in Narcissus": ("No" if is_not_in_narcissus else "Yes"),
                        "Age Threshold Reached": (f"Yes - {age.days} Days" if is_age_threshold_reached else "No"),
                    })

# Define Google Sheet URL
google_sheet_url = "https://docs.google.com/spreadsheets/d/1-OQn8DkE8z4IB50jqtWv-3INoYVprCg4ySBzInwSrHg/edit?usp=sharing"

spreadsheet_title = f"InstanceDetails({environment})"

# Opening or creating a Google Sheet
try:
    spreadsheet = gclient.open_by_url(google_sheet_url)
except gspread.exceptions.SpreadsheetNotFound:
    spreadsheet = gclient.create("Pipeline Instances")

spreadsheet.share("jfrog.com", perm_type="domain", role="reader")

try:
    worksheet = spreadsheet.worksheet(spreadsheet_title)
except:
    worksheet = spreadsheet.add_worksheet(title=spreadsheet_title, rows="100", cols="20")

worksheet.clear()

# Fetch the header row
header = worksheet.row_values(1)

worksheet.update('1:1', [header])
fieldnames = [tag_key, "InstanceID", "Name", "LaunchTime", "Region", "Type", "State", "Tags","Can Be Deleted","Customer Tag Missing", "Exist in Narcissus", "Age Threshold Reached"]
worksheet.insert_row(fieldnames, 1)
worksheet.format('1', {'textFormat': {'bold': True}})
worksheet.format('2', {'textFormat': {'bold': False}})

# Writing instance details to the Google Sheet
for idx, instance in enumerate(instance_details, start=2):
    row_values = [instance[field] for field in fieldnames]
    row_values.append("")
    
    # Initialize exponential backoff parameters
    retries = 0
    max_retries = 8  # Maximum number of retry attempts
    backoff_delay = 2  # Initial backoff delay in seconds
    
    while retries < max_retries:
        try:
            worksheet.insert_row(row_values, idx)
            break
        except Exception as e:
            sleep(backoff_delay)
            backoff_delay *= 2  # Exponential backoff: Double the delay
            retries += 1
    else:
        # If all retry attempts are exhausted, log an error
        print("Exceeded maximum retry attempts. Insertion failed.")

# Update the Google Sheet
google_sheet_url = spreadsheet.url

if instance_details:
    JIRA_ID = create_jira_for_orphaned(jira_base_url, jira_email, jira_token, instance_details)
    if JIRA_ID is None:
        print(f"Failed to create ticket for the orphaned instances")
    JIRA_URL = "https://jfrog-int.atlassian.net/browse/" + str(JIRA_ID)
    print(f"Google <{google_sheet_url}|Sheet> updated with instance details and created Ticket <{JIRA_URL}|Ticket>")
else:
    print(f"Google <{google_sheet_url}|Sheet> updated with instance details")
