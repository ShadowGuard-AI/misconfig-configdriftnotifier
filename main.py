import argparse
import time
import logging
import os
import yaml
import json
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import smtplib
from email.mime.text import MIMEText

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# Define constants
DEFAULT_CONFIG_FILE = 'config.yaml'

# --- Helper Functions ---

def load_config(config_file):
    """
    Loads configuration from a YAML file.

    Args:
        config_file (str): Path to the configuration file.

    Returns:
        dict: Configuration data.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        YAMLError: If the configuration file is not valid YAML.
    """
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {config_file}")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing configuration file: {e}")
        raise

def validate_config(config):
    """
    Validates the loaded configuration data.  Basic validation.  Expand as needed.

    Args:
        config (dict): Configuration data to validate.

    Returns:
        bool: True if the configuration is valid, False otherwise.  Raises exception on invalid config.

    Raises:
        ValueError: If required configuration parameters are missing or invalid.
    """
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary.")

    if 'monitored_files' not in config or not isinstance(config['monitored_files'], list):
        raise ValueError("Configuration must include 'monitored_files' as a list.")

    if 'notification' not in config or not isinstance(config['notification'], dict):
        raise ValueError("Configuration must include 'notification' settings.")

    if config['notification'].get('type') not in ('email', 'slack', None):
        raise ValueError("Notification type must be 'email' or 'slack', or None.")

    if config['notification'].get('type') == 'email':
        email_config = config['notification'].get('email')
        if not email_config:
            raise ValueError("Email configuration is required when notification type is email.")

        required_email_fields = ['sender', 'recipients', 'smtp_server', 'smtp_port']
        for field in required_email_fields:
            if field not in email_config or not email_config[field]:
                raise ValueError(f"Missing or empty email configuration field: {field}")
    # Add more validation rules as needed (e.g., slack validation)
    return True

def send_email_alert(subject, body, config):
    """
    Sends an email alert.

    Args:
        subject (str): Email subject.
        body (str): Email body.
        config (dict): Configuration data containing email settings.
    """
    email_config = config['notification']['email']
    sender = email_config['sender']
    recipients = email_config['recipients']
    smtp_server = email_config['smtp_server']
    smtp_port = email_config['smtp_port']
    smtp_user = email_config.get('smtp_user')
    smtp_password = email_config.get('smtp_password')

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)  # Consider using environment variables for credentials.
            server.sendmail(sender, recipients, msg.as_string())
        logging.info("Email alert sent successfully.")
    except Exception as e:
        logging.error(f"Error sending email alert: {e}")


def send_slack_alert(message, config):
    """
    Placeholder for sending Slack alerts.  Implement Slack integration here.

    Args:
        message (str): The message to send to Slack.
        config (dict): The configuration.
    """
    # TODO: Implement Slack integration using the Slack API or a library like `slack_sdk`.
    logging.warning("Slack integration not implemented yet.  Message: %s", message)
    print(f"Slack Alert (Not Implemented): {message}")  # For demonstration purposes

def lint_file(filepath, filetype):
    """
    Lints a file based on its file type using yamllint or jsonlint.

    Args:
        filepath (str): The path to the file.
        filetype (str): The file type (e.g., "yaml", "json").

    Returns:
        tuple: (True, None) if linting is successful, (False, error_message) if there's an error.
    """
    try:
        if filetype == "yaml":
            result = subprocess.run(['yamllint', filepath], capture_output=True, text=True, check=True)
            if result.returncode == 0:
                return True, None
            else:
                return False, f"yamllint failed with error: {result.stderr}"
        elif filetype == "json":
            result = subprocess.run(['jsonlint', filepath], capture_output=True, text=True, check=True)
            if result.returncode == 0:
                return True, None
            else:
                return False, f"jsonlint failed with error: {result.stderr}"
        else:
            return False, f"Unsupported file type: {filetype}"
    except FileNotFoundError as e:
        return False, f"Linter not found. Ensure yamllint/jsonlint is installed: {e}"
    except subprocess.CalledProcessError as e:
        return False, f"Linter process error: {e.stderr}"
    except Exception as e:
        return False, f"An unexpected error occurred during linting: {e}"

# --- Event Handler ---

class ConfigChangeHandler(FileSystemEventHandler):
    """
    Handles file system events, specifically configuration file changes.
    """

    def __init__(self, config):
        super().__init__()
        self.config = config

    def on_modified(self, event):
        """
        Called when a file or directory is modified.

        Args:
            event (watchdog.events.FileSystemEvent): The event object representing the file system event.
        """
        if event.is_directory:
            return  # Ignore directory changes

        filepath = event.src_path

        if filepath in self.config['monitored_files']:
            logging.info(f"Configuration file changed: {filepath}")

            # Determine file type based on extension (improve for content-based detection if needed)
            if filepath.endswith(('.yaml', '.yml')):
                filetype = "yaml"
            elif filepath.endswith('.json'):
                filetype = "json"
            else:
                filetype = "unknown"

            # Lint the file
            if filetype in ("yaml", "json"):
                lint_success, lint_message = lint_file(filepath, filetype)

                if not lint_success:
                    error_message = f"Configuration file {filepath} is invalid: {lint_message}"
                    logging.error(error_message)
                    self.send_alert(error_message)
                    return  # Stop processing further if linting fails

            try:
                # TODO: Add more sophisticated diffing logic here.  For now, just alert.
                message = f"Configuration file {filepath} has been modified. Linting: {lint_success}.  Message: {lint_message if lint_message else 'Linting Passed'}"
                self.send_alert(message)

            except Exception as e:
                logging.error(f"Error processing file change: {e}")

    def send_alert(self, message):
        """
        Sends an alert based on the configured notification method.

        Args:
            message (str): The alert message.
        """
        notification_type = self.config['notification'].get('type')

        if notification_type == 'email':
            send_email_alert("Configuration Drift Detected", message, self.config)
        elif notification_type == 'slack':
            send_slack_alert(message, self.config) # Call Slack Function
        else:
            logging.warning("No notification method configured.")


# --- Argument Parsing ---

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.

    Returns:
        argparse.ArgumentParser: The argument parser.
    """
    parser = argparse.ArgumentParser(description="Monitors configuration files for changes and sends alerts.")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_FILE,
                        help="Path to the configuration file. Defaults to config.yaml")
    return parser

# --- Main Function ---

def main():
    """
    Main function to start the configuration drift notifier.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        validate_config(config) # Validate after loading.
    except Exception as e:
        print(f"Configuration error: {e}")
        exit(1)


    # Sanitize file paths (example: removing ../../ tricks - simplistic)
    monitored_files = config['monitored_files']
    sanitized_files = []
    for file_path in monitored_files:
        abs_path = os.path.abspath(file_path) # Get the real absolute path
        if not abs_path.startswith(os.getcwd()):
             logging.warning(f"Path {file_path} resolves to outside the current directory.  Sanitizing to be inside.")
             sanitized_files.append(os.path.basename(file_path)) #Just use file name to be secure
        else:
            sanitized_files.append(file_path)

    config['monitored_files'] = sanitized_files # Update config

    event_handler = ConfigChangeHandler(config)
    observer = Observer()

    # Determine the directories to watch
    directories_to_watch = set()
    for file_path in config['monitored_files']:
        directories_to_watch.add(os.path.dirname(os.path.abspath(file_path)))

    for directory in directories_to_watch:
       observer.schedule(event_handler, directory, recursive=False)

    observer.start()

    try:
        while True:
            time.sleep(1)  # Check for interrupt every second
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# --- Run the main function ---

if __name__ == "__main__":
    main()


"""
Usage Examples:

1.  Basic Usage:
    python main.py

    Assumes a config.yaml file exists in the same directory.

2.  Specifying a Configuration File:
    python main.py -c my_config.yaml

    Uses the my_config.yaml file for configuration.

3. Email example config
notification:
  type: email
  email:
    sender: "sender@example.com"
    recipients: ["recipient1@example.com", "recipient2@example.com"]
    smtp_server: "smtp.example.com"
    smtp_port: 587
    smtp_user: "smtp_username" #Optional
    smtp_password: "smtp_password" #Optional - IMPORTANT:  Consider using environment variables!

4.  Slack Placeholder example config
notification:
  type: slack

monitored_files:
  - "config.yaml"
  - "another_config.json"
"""