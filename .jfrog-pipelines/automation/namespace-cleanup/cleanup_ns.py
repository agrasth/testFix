import argparse
import datetime
import pytz
import re
import requests
import json
from kubernetes import client, config

def check_for_old_namespaces(client, days):
    to_ignore = ['ccert', 'cert-manager', 'default','ingress-nginx', 'kube-node-lease', 'kube-public', 'kube-system', 'pipe-master-pool', 'master']
    to_report = {}
    v1 = client.CoreV1Api()
    current_time = datetime.datetime.now(pytz.UTC)

    # Get all namespaces
    namespaces = v1.list_namespace().items

    for namespace in namespaces:
        namespace_creation_time = namespace.metadata.creation_timestamp
        age = current_time - namespace_creation_time

        if age.days >= days and namespace.metadata.name not in to_ignore:
            to_report[namespace.metadata.name] = {'age': age.days, 'assignee': ''}
    
    return to_report

def get_issue_details(jira_base_url, jira_email, jira_token, issue_id):
    # Construct the URL for the issue endpoint
    issue_url = f"{jira_base_url}issue/{issue_id}"
    
    # Set up basic authentication
    auth = (jira_email, jira_token)
    
    try:
        # Make the API request
        response = requests.get(issue_url, auth=auth, headers={"Content-Type": "application/json"})
        
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            assignee_name = data['fields']['assignee']['emailAddress'].split('@')[0]
            jira_status  = data['fields']['status']['name']
            return assignee_name,jira_status
        else:
            return None, None
    except Exception as e:
        print(f"An error occurred: {e} with issue ID {issue_id}")
        return None, None
    

def delete_namespace(client, namespace):
    v1 = client.CoreV1Api()
    try:
        v1.delete_namespace(namespace)
        return True
    except Exception as e:
        print(f"An Error occured while deleting the namespace: {e}")
        return False


def main():
    reporting_data = {}
    parser = argparse.ArgumentParser(description='Check Kubernetes namespaces older than a certain number of days')
    parser.add_argument('days', type=int, help='Number of days to consider namespaces as old')
    parser.add_argument('jira_base_url', help='Jira base URL')
    parser.add_argument('jira_email', help='Jira email')
    parser.add_argument('jira_token', help='Jira API token')
    args = parser.parse_args()

    # Load the Kubernetes config from the default location
    config.load_kube_config()

    # Check old namespaces
    to_report = check_for_old_namespaces(client, args.days)
    for namespace in to_report:
        assignee_name,jira_status = get_issue_details(args.jira_base_url, args.jira_email, args.jira_token, "PIPE-"+namespace[1:])
        if assignee_name is not None:
            to_report[namespace]['assignee'] = assignee_name
            to_report[namespace]['jira_status'] = jira_status
            if jira_status == "Done" or jira_status == "Closed":
                if delete_namespace(client, namespace):
                    to_report[namespace]['ns_status'] = "DELETED"
                else:
                    to_report[namespace]['ns_status'] = "Couldn't DELETE"
            else:
                to_report[namespace]['ns_status'] = "Ticket Pending"
        else:
            to_report[namespace]['assignee'] = "Unknown"
    
    
    # Print namespaces data in a pretty format
    print("Namespace\tAge (days)\tOwner\tTicket Status\tNamespace Status")
    print("-------------------------------------------------------------")
    for namespace, data in to_report.items():
        if data['assignee'] != "Unknown":
            print(f"{namespace}\t\t{data['age']}\t\t<@{data['assignee']}>\t{data['jira_status']}\t\t{data['ns_status']}")
        else:
            print(f"{namespace}\t\t{data['age']}\t\t{data['assignee']}")

if __name__ == "__main__":
    main()
