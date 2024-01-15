import boto3
import argparse
import csv
import os
from datetime import datetime, timedelta
import gspread
from time import sleep
from oauth2client.service_account import ServiceAccountCredentials
# import psycopg2
import pytz
import requests
import json

# Google Sheets API setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gclient = gspread.authorize(credentials)



parser = argparse.ArgumentParser(description='List non-terminated instances matching a specific tag')
parser.add_argument('--access-key', help='AWS Access Key')
parser.add_argument('--secret-key', help='AWS Secret Key')
parser.add_argument('--tag-key', required=True, help='Tag Key to Filter instances')
parser.add_argument('--tag-value', required=True, help='Value for the Tag to filter')
parser.add_argument('--environment', required=True, help='Environment to Run the script')
parser.add_argument('--jira_base_url', help='Jira base URL')
parser.add_argument('--jira_email', help='Jira email')
parser.add_argument('--jira_token', help='Jira API token')



# parser.add_argument('--db-name', default='jfrogrepo21_jfpl', help='Database name')
# parser.add_argument('--db-user', required=True, help='Database user')
# parser.add_argument('--db-password', required=True, help='Database password')
# parser.add_argument('--db-host', default='localhost', help='Database host')
# parser.add_argument('--db-port', default='10022', help='Database port')


parser.add_argument('--jpd-endpoint', default='https://entplus.jfrog.io', help='Customer Endpoint')
parser.add_argument('--jpd-user-access-token', required=True, help='JPD User Access Token')

args = parser.parse_args()

environment = args.environment

# Set the tag key and value to filter instances
tag_key =  args.tag_key
tag_value = args.tag_value

jira_base_url = args.jira_base_url
jira_email = args.jira_email
jira_token = args.jira_token

# Set the list of regions to check
regions = ["us-east-1", "eu-central-1", "ap-south-1"]  # Add more regions as needed

# Initialize an empty list to store instance details
instance_details = []

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
                "key": "PE"
            },
            "summary": "Please delete the Instances (Orphaned pipeline's nodes)",
            "description": f"Please delete the following instances:\n{table_header}\n{table_rows}",
            "issuetype": {
                "name": "Task"
            },
            "customfield_10129":[
                {
                    "value": "PE-India"
                },
            ],
            "timetracking":{
                "originalEstimate": "4h"
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


def get_nodes(api_token, nodes_api_endpoint):
    api_endpoint = f"{nodes_api_endpoint}/pipelines/api/v1/nodes"

    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    try:
        response = requests.get(api_endpoint, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"An error occurred while calling the get/nodes API: {str(e)}")
        return None

def orphaned_instances():
    nodes = get_nodes(args.jpd_user_access_token, args.jpd_endpoint)
    instances_with_deletedAT_not_null = set()
    instances_in_pipelines = []
    instances_to_delete = []

    for instance in nodes:
        instance_id = instance.get("instanceId")
        deleted_at = instance.get("deletedAt")
        if instance_id is not None:
            instances_in_pipelines.append(instance_id)

        if instance_id is not None and deleted_at is not None:
            instances_with_deletedAT_not_null.add(instance_id)


    for instance in instance_details:
        instance_id = instance["InstanceID"].replace('"',"'")
        if instance_id in instances_in_pipelines:
            if instance_id in instances_with_deletedAT_not_null:
                instance["Can Be Deleted"] = "Yes"
                instance["Deletion Reason"] = "deletedAt is not NULL"
                instances_to_delete.append(instance)
        else:
            instance["Can Be Deleted"] = "Yes"
            instance["Deletion Reason"] = "Instance does not exist in get/nodes API response"
            instances_to_delete.append(instance)

    return instances_to_delete

def filter_orphaned_instances():
    instances_to_delete_1 = orphaned_instances()
    sleep(300)
    instances_to_delete_2 = orphaned_instances()

    instances_1 = [d["InstanceID"] for d in instances_to_delete_1]
    instances_2 = [d["InstanceID"] for d in instances_to_delete_2]

    # Find the common ids between the two arrays
    common_instances = set(instances_1) & set(instances_2)

    # Get the dictionary entries with common ids
    final_ophaned_instances = [d for d in instances_to_delete_1 + instances_to_delete_2 if d["InstanceID"] in common_instances]

    return final_ophaned_instances

# Iterate over the specified regions
for region_name in regions:
    if args.access_key is not None and args.secret_key is not None:
        ec2 = boto3.client("ec2", region_name=region_name, aws_access_key_id=args.access_key, aws_secret_access_key=args.secret_key)
    else:
        ec2 = boto3.client("ec2", region_name=region_name)
    
    # Get instances with the specified tag and filter by termination status
    response = ec2.describe_instances(Filters=[{"Name": f"tag:{tag_key}", "Values": [tag_value]}, {"Name": f"tag-key", "Values": ["Node Pool Id"]},])
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"]["Name"] != "terminated" and instance["State"]["Name"] != "shutting-down":
                launch_time = instance["LaunchTime"]
                current_time = datetime.now(launch_time.tzinfo)

                if instance["State"]["Name"] == "stopped":
                    stop_time = current_time
                else:
                    stop_reason = instance.get('StateTransitionReason')
                    if stop_reason != '':
                        date_time_str = stop_reason.split('(')[1].split(')')[0].strip()
                        stop_time = datetime.strptime(date_time_str, "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=launch_time.tzinfo)
                    else:
                        stop_time = launch_time


                age = current_time - launch_time
                running_for = current_time - stop_time
                running_for_hours, remainder = divmod(running_for.seconds, 3600)
                running_for_minutes, running_for_seconds = divmod(remainder, 60)

                instance_details.append({
                    tag_key: tag_value,
                    "InstanceID": instance["InstanceId"],
                    "Name": next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"), "N/A"),
                    "LaunchTime": launch_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "Region": region_name,
                    "Type": instance["InstanceType"],
                    "State": instance["State"]["Name"],
                    "Tags": str(instance["Tags"]),
                    "Can Be Deleted": "No",
                    "Running for": f"{running_for_hours} Hours {running_for_minutes} minutes {running_for_seconds} seconds"
                })

# db_params = {
#     'dbname': args.db_name,
#     'user': args.db_user,
#     'password': args.db_password,
#     'host': args.db_host,
#     'port': args.db_port
# }

# instances_to_delete = []

# try:
#     conn = psycopg2.connect(**db_params)

#     for instance in instance_details:
#         instance_id = instance["InstanceID"].replace('"',"'")
#         cursor = conn.cursor()
#         try:
#             cursor.execute("SELECT * FROM public.\"nodes\" WHERE public.\"nodes\".\"instanceId\" = %s", (instance_id,))
#             columns = [desc[0] for desc in cursor.description]
#             row = cursor.fetchone()

#             if row is None:
#                 print("Row not found in the table.")
#                 instance["Can Be Deleted"] = "Yes"
#                 instance["Deletion Reason"] = "Instance does not exist in Nodes Table"
#                 instances_to_delete.append(instance)
#                 continue
#             else:
#                 row_dict = dict(zip(columns, row))
#                 if row_dict['deletedAt'] is not None:
#                     instance["Can Be Deleted"] = "Yes"
#                     instance["Deletion Reason"] = "deletedAt is not NULL"
#                     instances_to_delete.append(instance)
#                     continue
#         except (Exception, psycopg2.Error) as error:
#             print(f"Error for instance ID {instance_id}: {error}")
#         finally:
#             cursor.close()

# except (Exception, psycopg2.Error) as error:
#     print("Error connecting to the database:", error)

# finally:
#     if conn:
#         conn.close()


instances_to_delete = filter_orphaned_instances()


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

all_values = worksheet.get_all_values()
last_empty_row = len(all_values) + 3

worksheet.insert_row([datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S")], last_empty_row)
fieldnames = [tag_key, "InstanceID", "Name", "LaunchTime", "Region", "Type", "State", "Tags","Can Be Deleted", "Deletion Reason","Running for"]
worksheet.insert_row(fieldnames, last_empty_row+1)
worksheet.format(str(last_empty_row+1), {'textFormat': {'bold': True}})

# Writing instance details to the Google Sheet
for idx, instance in enumerate(instances_to_delete, start=last_empty_row+2):
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

if instances_to_delete:
    JIRA_ID = create_jira_for_orphaned(jira_base_url, jira_email, jira_token, instances_to_delete)
    if JIRA_ID is None:
        print(f"Failed to create ticket for the orphaned instances")
    JIRA_URL = "https://jfrog-int.atlassian.net/browse/" + str(JIRA_ID)
    print(f"Google <{google_sheet_url}|Sheet> updated with instance details and created <{JIRA_URL}|Ticket>")
else:
    print(f"Google <{google_sheet_url}|Sheet> updated with instance details")


# To run the script - 
# --access-key <access-key-id>  --secret-key <secret-key> these args can be ignored if AWS tokens are added to your terminal
# python3 orphaned-nodes-manual-check.py --access-key <access-key-id>  --secret-key <secret-key> --environment "PROD" --tag-key "Customer Name" --tag-value "jfrogrepo21" --db-name 'jfrogrepo21_jfpl' --db-user <db-user> --db-password <db-password> --db-host localhost --db-port <db-port>