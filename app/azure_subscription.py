from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.core.exceptions import AzureError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_subscription_info(subscription_id: str):
    """
    Get information about a specific Azure subscription.
    
    Args:
        subscription_id: The ID of the subscription to query
        
    Returns:
        dict: Subscription details if successful
    """
    try:
        # Create credential object - DefaultAzureCredential tries multiple authentication methods
        credential = DefaultAzureCredential()
        
        # Create the subscription client
        subscription_client = SubscriptionClient(credential)
        
        # Get the subscription details
        subscription = subscription_client.subscriptions.get(subscription_id)
        
        logger.info(f"Successfully retrieved subscription information")
        
        return {
            "subscription_id": subscription.subscription_id,
            "display_name": subscription.display_name,
            "state": subscription.state
        }
        
    except AzureError as e:
        logger.error(f"Error accessing subscription: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise

def main():
    # Your subscription ID
    subscription_id = "5ebfa7cd-3b83-4a77-8928-b5c5b92232f9"
    
    try:
        subscription_info = get_subscription_info(subscription_id)
        print("\nSubscription Details:")
        print(f"ID: {subscription_info['subscription_id']}")
        print(f"Name: {subscription_info['display_name']}")
        print(f"State: {subscription_info['state']}")
        
    except Exception as e:
        print(f"Failed to get subscription information: {str(e)}")

if __name__ == "__main__":
    main()