"""
Notification Services for Enterprise LMS
Provides NotificationService for multi-channel notification delivery (email, in-app, push).
"""

import logging
import json
import base64
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.core.services import EncryptionVerificationService

logger = logging.getLogger(__name__)
User = get_user_model()


class ProviderType(Enum):
    """Email provider types."""
    SENDGRID = 'sendgrid'
    AWS_SES = 'aws_ses'


class EmailStatus(Enum):
    """Email delivery status."""
    PENDING = 'pending'
    QUEUED = 'queued'
    SENT = 'sent'
    DELIVERED = 'delivered'
    OPENED = 'opened'
    CLICKED = 'clicked'
    BOUNCED = 'bounced'
    COMPLAINED = 'complained'
    FAILED = 'failed'
    DEFERRED = 'deferred'
    DROPPED = 'dropped'
    PROCESSED = 'processed'


@dataclass
class EmailResult:
    """Result of an email send attempt."""
    success: bool
    provider: Optional[str]
    message_id: Optional[str]
    error_message: Optional[str]
    response_data: Optional[Dict] = None


class SendGridClient:
    """SendGrid API client wrapper."""
    
    BASE_URL = "https://api.sendgrid.com/v3"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict]] = None,
        categories: Optional[List[str]] = None,
        custom_args: Optional[Dict] = None,
        send_at: Optional[datetime] = None
    ) -> EmailResult:
        """Send email via SendGrid API."""
        try:
            from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            from_name = from_name or getattr(settings, 'SITE_NAME', 'LMS')
            
            # Build personalization
            personalization = {
                "to": [{"email": to_email}]
            }
            
            if cc:
                personalization["cc"] = [{"email": e} for e in cc]
            if bcc:
                personalization["bcc"] = [{"email": e} for e in bcc]
            if custom_args:
                personalization["custom_args"] = custom_args
            if send_at:
                personalization["send_at"] = int(send_at.timestamp())
            
            # Build message content
            content = [{"type": "text/plain", "value": text_content}]
            if html_content:
                content.append({"type": "text/html", "value": html_content})
            
            # Build payload
            payload = {
                "personalizations": [personalization],
                "from": {"email": from_email, "name": from_name},
                "subject": subject,
                "content": content
            }
            
            if reply_to:
                payload["reply_to"] = {"email": reply_to}
            
            if attachments:
                payload["attachments"] = [
                    {
                        "content": base64.b64encode(att['content']).decode(),
                        "filename": att['filename'],
                        "type": att.get('mimetype', 'application/octet-stream'),
                        "disposition": "attachment"
                    }
                    for att in attachments
                ]
            
            if categories:
                payload["categories"] = categories
            
            # Send request
            response = requests.post(
                f"{self.BASE_URL}/mail/send",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 202:
                # Extract message ID from headers
                message_id = response.headers.get('X-Message-Id', '')
                return EmailResult(
                    success=True,
                    provider='sendgrid',
                    message_id=message_id,
                    error_message=None,
                    response_data={'status_code': response.status_code}
                )
            else:
                error_data = response.json() if response.content else {}
                return EmailResult(
                    success=False,
                    provider='sendgrid',
                    message_id=None,
                    error_message=f"SendGrid error {response.status_code}: {error_data}",
                    response_data=error_data
                )
                
        except requests.exceptions.Timeout:
            return EmailResult(
                success=False,
                provider='sendgrid',
                message_id=None,
                error_message="SendGrid API timeout"
            )
        except Exception as e:
            return EmailResult(
                success=False,
                provider='sendgrid',
                message_id=None,
                error_message=f"SendGrid error: {str(e)}"
            )
    
    def get_reputation(self) -> Dict[str, Any]:
        """Get SendGrid account reputation metrics."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/user/account",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'reputation_score': data.get('reputation', 0),
                    'daily_send_limit': data.get('usage', {}).get('allowed', 0),
                    'daily_sent': data.get('usage', {}).get('used', 0),
                    'is_healthy': data.get('reputation', 0) > 80
                }
            return {'error': f'HTTP {response.status_code}', 'is_healthy': False}
        except Exception as e:
            return {'error': str(e), 'is_healthy': False}
    
    def validate_webhook_signature(self, payload: bytes, signature: str, timestamp: str) -> bool:
        """Validate SendGrid webhook signature."""
        try:
            # Get webhook public key from settings
            public_key = getattr(settings, 'SENDGRID_WEBHOOK_PUBLIC_KEY', '')
            if not public_key:
                return False
            
            # Construct signed content
            signed_content = timestamp.encode() + payload
            expected_signature = base64.b64encode(
                hashlib.sha256(signed_content).digest()
            ).decode()
            
            return signature == expected_signature
        except Exception:
            return False


class AWSSESClient:
    """AWS SES API client wrapper."""
    
    def __init__(self, access_key: str, secret_key: str, region: str = 'us-east-1'):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.base_url = f"https://email.{region}.amazonaws.com"
    
    def _sign_request(self, payload: str, timestamp: str) -> Dict[str, str]:
        """Sign AWS SES request."""
        date_stamp = timestamp[:8]
        
        # Create canonical request
        canonical_request = f"POST\n/\n\nhost:email.{self.region}.amazonaws.com\n\nhost\n{hashlib.sha256(payload.encode()).hexdigest()}"
        
        # Create string to sign
        credential_scope = f"{date_stamp}/{self.region}/ses/aws4_request"
        string_to_sign = f"AWS4-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        
        # Calculate signature
        def hmac_sha256(key, msg):
            return hashlib.new('sha256', msg.encode(), key).digest()
        
        date_key = hmac_sha256(f"AWS4{self.secret_key}".encode(), date_stamp)
        region_key = hmac_sha256(date_key, self.region)
        service_key = hmac_sha256(region_key, 'ses')
        signing_key = hmac_sha256(service_key, 'aws4_request')
        signature = hmac_sha256(signing_key, string_to_sign).hex()
        
        return {
            'Authorization': f"AWS4-HMAC-SHA256 Credential={self.access_key}/{credential_scope}, SignedHeaders=host, Signature={signature}",
            'Date': timestamp,
            'X-Amz-Date': timestamp
        }
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict]] = None,
        configuration_set: Optional[str] = None
    ) -> EmailResult:
        """Send email via AWS SES API."""
        try:
            from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            from_name = from_name or getattr(settings, 'SITE_NAME', 'LMS')
            
            # Build message
            message = {
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': text_content}
                }
            }
            
            if html_content:
                message['Body']['Html'] = {'Data': html_content}
            
            # Build destination
            destination = {'ToAddresses': [to_email]}
            if cc:
                destination['CcAddresses'] = cc
            if bcc:
                destination['BccAddresses'] = bcc
            
            # Build source
            source = f"{from_name} <{from_email}>" if from_name else from_email
            
            # Build request payload
            payload = {
                'Action': 'SendEmail',
                'Source': source,
                'Destination': json.dumps(destination),
                'Message': json.dumps(message)
            }
            
            if reply_to:
                payload['ReplyToAddresses'] = reply_to
            
            if configuration_set:
                payload['ConfigurationSetName'] = configuration_set
            
            # Encode payload
            encoded_payload = '&'.join([f"{k}={requests.utils.quote(v)}" for k, v in payload.items()])
            
            # Sign request
            timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            headers = self._sign_request(encoded_payload, timestamp)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            # Send request
            response = requests.post(
                self.base_url,
                data=encoded_payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                # Parse message ID from response
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                message_id = root.find('.//MessageId')
                message_id = message_id.text if message_id is not None else None
                
                return EmailResult(
                    success=True,
                    provider='aws_ses',
                    message_id=message_id,
                    error_message=None,
                    response_data={'status_code': response.status_code}
                )
            else:
                return EmailResult(
                    success=False,
                    provider='aws_ses',
                    message_id=None,
                    error_message=f"SES error {response.status_code}: {response.text}",
                    response_data={'response': response.text}
                )
                
        except requests.exceptions.Timeout:
            return EmailResult(
                success=False,
                provider='aws_ses',
                message_id=None,
                error_message="AWS SES API timeout"
            )
        except Exception as e:
            return EmailResult(
                success=False,
                provider='aws_ses',
                message_id=None,
                error_message=f"SES error: {str(e)}"
            )
    
    def get_reputation(self) -> Dict[str, Any]:
        """Get AWS SES account reputation metrics."""
        try:
            # SES v2 API for reputation
            timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            payload = 'Action=GetSendQuota'
            headers = self._sign_request(payload, timestamp)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            response = requests.post(
                self.base_url,
                data=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                max_24h = root.find('.//Max24HourSend')
                sent_24h = root.find('.//SentLast24Hours')
                max_rate = root.find('.//MaxSendRate')
                
                return {
                    'max_24h_send': float(max_24h.text) if max_24h is not None else 0,
                    'sent_24h': float(sent_24h.text) if sent_24h is not None else 0,
                    'max_send_rate': float(max_rate.text) if max_rate is not None else 0,
                    'is_healthy': True  # SES doesn't expose reputation score directly
                }
            return {'error': f'HTTP {response.status_code}', 'is_healthy': False}
        except Exception as e:
            return {'error': str(e), 'is_healthy': False}


class EmailProviderManager:
    """Manages email providers with failover logic."""
    
    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._health_scores: Dict[str, float] = {}
        self._last_health_check: Dict[str, datetime] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize configured email providers."""
        # SendGrid
        sendgrid_key = getattr(settings, 'SENDGRID_API_KEY', None)
        if sendgrid_key:
            self._providers['sendgrid'] = SendGridClient(sendgrid_key)
            self._health_scores['sendgrid'] = 100.0
        
        # AWS SES
        aws_access_key = getattr(settings, 'AWS_SES_ACCESS_KEY', None)
        aws_secret_key = getattr(settings, 'AWS_SES_SECRET_KEY', None)
        aws_region = getattr(settings, 'AWS_SES_REGION', 'us-east-1')
        if aws_access_key and aws_secret_key:
            self._providers['aws_ses'] = AWSSESClient(aws_access_key, aws_secret_key, aws_region)
            self._health_scores['aws_ses'] = 100.0
    
    def get_provider(self, provider_name: Optional[str] = None) -> Tuple[str, Any]:
        """Get the best available provider."""
        if provider_name and provider_name in self._providers:
            return provider_name, self._providers[provider_name]
        
        # Sort by health score and return best
        if not self._providers:
            raise RuntimeError("No email providers configured")
        
        sorted_providers = sorted(
            self._providers.items(),
            key=lambda x: self._health_scores.get(x[0], 0),
            reverse=True
        )
        
        # Filter out unhealthy providers
        healthy_providers = [
            (name, client) for name, client in sorted_providers
            if self._health_scores.get(name, 0) > 50
        ]
        
        if healthy_providers:
            return healthy_providers[0]
        
        # Fallback to any available provider
        return sorted_providers[0]
    
    def update_health_score(self, provider_name: str, success: bool):
        """Update provider health score based on send result."""
        current_score = self._health_scores.get(provider_name, 100.0)
        
        if success:
            # Gradually recover health
            new_score = min(100.0, current_score + 5.0)
        else:
            # Penalize failures more heavily
            new_score = max(0.0, current_score - 20.0)
        
        self._health_scores[provider_name] = new_score
        logger.info(f"Updated health score for {provider_name}: {current_score:.1f} -> {new_score:.1f}")
    
    def check_provider_health(self, provider_name: str) -> Dict[str, Any]:
        """Check health of a specific provider."""
        if provider_name not in self._providers:
            return {'error': 'Provider not configured', 'is_healthy': False}
        
        client = self._providers[provider_name]
        reputation = client.get_reputation()
        
        self._last_health_check[provider_name] = timezone.now()
        
        return {
            'provider': provider_name,
            'health_score': self._health_scores.get(provider_name, 0),
            'reputation': reputation,
            'is_healthy': reputation.get('is_healthy', False)
        }
    
    def get_all_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all providers."""
        return {
            name: self.check_provider_health(name)
            for name in self._providers.keys()
        }


class EmailService:
    """
    Enhanced email service with provider abstraction, automatic failover,
    and comprehensive delivery tracking.
    """
    
    _instance = None
    _provider_manager = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._provider_manager = EmailProviderManager()
        return cls._instance
    
    def __init__(self):
        self.provider_manager = self._provider_manager
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Tuple[str, bytes, str]]] = None,
        categories: Optional[List[str]] = None,
        custom_args: Optional[Dict] = None,
        send_at: Optional[datetime] = None,
        preferred_provider: Optional[str] = None,
        track_opens: bool = True,
        track_clicks: bool = True,
        template_id: Optional[str] = None
    ) -> EmailResult:
        """
        Send an email with automatic provider failover.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            text_content: Plain text content
            html_content: HTML content (optional)
            from_email: Sender email address
            from_name: Sender display name
            reply_to: Reply-to address
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of (filename, content, mimetype) tuples
            categories: Email categories for tracking
            custom_args: Custom arguments for tracking
            send_at: Scheduled send time
            preferred_provider: Preferred provider name
            track_opens: Whether to track email opens
            track_clicks: Whether to track link clicks
            template_id: Template ID for tracking
            
        Returns:
            EmailResult with success status and details
        """
        # Try preferred provider first
        providers_to_try = []
        
        if preferred_provider:
            providers_to_try.append(preferred_provider)
        
        # Add all other providers sorted by health
        all_providers = sorted(
            self.provider_manager._providers.keys(),
            key=lambda x: self.provider_manager._health_scores.get(x, 0),
            reverse=True
        )
        
        for provider in all_providers:
            if provider not in providers_to_try:
                providers_to_try.append(provider)
        
        last_error = None
        
        for provider_name in providers_to_try:
            try:
                _, client = self.provider_manager.get_provider(provider_name)
                
                # Convert attachments format
                formatted_attachments = None
                if attachments:
                    formatted_attachments = [
                        {'filename': name, 'content': content, 'mimetype': mtype}
                        for name, content, mtype in attachments
                    ]
                
                # Send via provider
                result = client.send_email(
                    to_email=to_email,
                    subject=subject,
                    text_content=text_content,
                    html_content=html_content,
                    from_email=from_email,
                    from_name=from_name,
                    reply_to=reply_to,
                    cc=cc,
                    bcc=bcc,
                    attachments=formatted_attachments,
                    categories=categories,
                    custom_args=custom_args,
                    send_at=send_at
                )
                
                # Update health score
                self.provider_manager.update_health_score(provider_name, result.success)
                
                if result.success:
                    logger.info(f"Email sent successfully via {provider_name}: {subject}")
                    return result
                else:
                    last_error = result.error_message
                    logger.warning(f"Provider {provider_name} failed: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                self.provider_manager.update_health_score(provider_name, False)
                logger.error(f"Provider {provider_name} error: {last_error}")
        
        # All providers failed
        return EmailResult(
            success=False,
            provider=None,
            message_id=None,
            error_message=f"All providers failed. Last error: {last_error}"
        )
    
    def send_template_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        from_email: Optional[str] = None,
        **kwargs
    ) -> EmailResult:
        """
        Send an email using a Django template.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            template_name: Name of the template (without extension)
            context: Template context dictionary
            from_email: Sender email address
            **kwargs: Additional arguments for send_email
            
        Returns:
            EmailResult with success status
        """
        try:
            text_content = render_to_string(f'emails/{template_name}.txt', context)
            html_content = render_to_string(f'emails/{template_name}.html', context)
        except:
            # Fallback if template doesn't exist
            text_content = context.get('message', '')
            html_content = f"<html><body>{context.get('message', '')}</body></html>"
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            from_email=from_email,
            **kwargs
        )
    
    def send_bulk_emails(
        self,
        recipients: List[Dict[str, Any]],
        batch_size: int = 100,
        throttle_ms: int = 100
    ) -> Dict[str, Any]:
        """
        Send emails to multiple recipients with throttling.
        
        Args:
            recipients: List of recipient dicts with email, subject, content, etc.
            batch_size: Number of emails per batch
            throttle_ms: Milliseconds to wait between batches
            
        Returns:
            Dict with success count, failure count, and details
        """
        results = {
            'total': len(recipients),
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        for i, recipient in enumerate(recipients):
            try:
                result = self.send_email(**recipient)
                
                if result.success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                
                results['details'].append({
                    'email': recipient.get('to_email'),
                    'success': result.success,
                    'provider': result.provider,
                    'message_id': result.message_id,
                    'error': result.error_message
                })
                
                # Throttle between batches
                if (i + 1) % batch_size == 0:
                    time.sleep(throttle_ms / 1000)
                    
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'email': recipient.get('to_email'),
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    def get_provider_health(self) -> Dict[str, Any]:
        """Get health status for all configured providers."""
        return self.provider_manager.get_all_health_status()
    
    def get_recommended_provider(self) -> Optional[str]:
        """Get the currently recommended provider based on health scores."""
        try:
            name, _ = self.provider_manager.get_provider()
            return name
        except RuntimeError:
            return None


class NotificationService:
    """
    Service for sending notifications through multiple channels.
    Supports email (SMTP/SES/SendGrid), in-app (WebSocket/SSE), and push notifications.
    """
    
    def __init__(self):
        self.encryption_service = EncryptionVerificationService()
        self.email_service = EmailService()
    
    def send_notification(
        self,
        user: User,
        title: str,
        message: str,
        notification_type: str = 'in_app',
        category: str = 'general',
        priority: str = 'normal',
        data: Optional[Dict[str, Any]] = None,
        action_url: str = '',
        send_email: bool = True,
        send_push: bool = False
    ) -> 'Notification':
        """
        Send a notification to a user through specified channels.
        
        Args:
            user: The user to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification (email, in_app, push)
            category: Category of notification
            priority: Priority level (low, normal, high, urgent)
            data: Additional data as JSON
            action_url: URL to navigate to when clicked
            send_email: Whether to also send email
            send_push: Whether to also send push notification
            
        Returns:
            The created Notification instance
        """
        from .models import Notification
        
        # Create the notification record
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            category=category,
            priority=priority,
            title=title,
            message=message,
            data=data or {},
            action_url=action_url,
            status=Notification.STATUS_PENDING
        )
        
        # Check user preferences
        try:
            preferences = user.notification_preferences
        except:
            preferences = None
        
        # Send through appropriate channels
        if notification_type == Notification.TYPE_EMAIL or send_email:
            if not preferences or preferences.should_send_email(category):
                if not preferences or not preferences.is_quiet_hours():
                    self._send_email_notification(notification)
        
        if notification_type == Notification.TYPE_IN_APP:
            self._send_in_app_notification(notification)
        
        if notification_type == Notification.TYPE_PUSH or send_push:
            if not preferences or preferences.should_send_push(category):
                self._send_push_notification(notification)
        
        return notification
    
    def _send_email_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via email using the enhanced EmailService.
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Prepare email context
            context = {
                'notification': notification,
                'user': notification.user,
                'site_name': getattr(settings, 'SITE_NAME', 'LMS'),
                'site_url': getattr(settings, 'SITE_URL', ''),
            }
            
            # Render email templates
            subject = notification.title
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            to_email = notification.user.email
            
            # Plain text version
            text_content = notification.message
            
            # HTML version
            try:
                html_content = render_to_string('emails/notification.html', context)
            except:
                # Fallback if template doesn't exist
                html_content = f"""
                <html>
                <body>
                    <h2>{notification.title}</h2>
                    <p>{notification.message}</p>
                    {f'<a href="{notification.action_url}">View Details</a>' if notification.action_url else ''}
                </body>
                </html>
                """
            
            # Send via enhanced EmailService with failover
            result = self.email_service.send_email(
                to_email=to_email,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                from_email=from_email,
                categories=[notification.category],
                custom_args={'notification_id': str(notification.id)}
            )
            
            if result.success:
                notification.mark_as_sent()
                logger.info(f"Email notification sent to {to_email} via {result.provider}: {notification.title}")
                return True
            else:
                notification.mark_as_failed(result.error_message or "Unknown error")
                logger.error(f"Failed to send email notification: {result.error_message}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def _send_in_app_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via in-app (WebSocket/SSE).
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Mark as sent (in-app notifications are immediately available)
            notification.mark_as_sent()
            notification.mark_as_delivered()
            
            # TODO: Implement WebSocket/SSE push via Django Channels
            # This would typically involve:
            # from channels.layers import get_channel_layer
            # from asgiref.sync import async_to_sync
            # channel_layer = get_channel_layer()
            # async_to_sync(channel_layer.group_send)(
            #     f"user_{notification.user.id}_notifications",
            #     {
            #         "type": "notification_message",
            #         "notification": {
            #             "id": str(notification.id),
            #             "title": notification.title,
            #             "message": notification.message,
            #             "category": notification.category,
            #             "created_at": notification.created_at.isoformat(),
            #         }
            #     }
            # )
            
            logger.info(f"In-app notification sent to user {notification.user.id}: {notification.title}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send in-app notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def _send_push_notification(self, notification: 'Notification') -> bool:
        """
        Send notification via push notification service.
        
        Args:
            notification: The notification to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get user's push tokens
            try:
                preferences = notification.user.notification_preferences
                device_tokens = preferences.push_device_tokens if preferences else []
            except:
                device_tokens = []
            
            if not device_tokens:
                logger.warning(f"No push tokens for user {notification.user.id}")
                return False
            
            # TODO: Implement push notification via Firebase Cloud Messaging or similar
            # This would typically involve:
            # import firebase_admin
            # from firebase_admin import messaging
            # for token in device_tokens:
            #     message = messaging.Message(
            #         notification=messaging.Notification(
            #             title=notification.title,
            #             body=notification.message,
            #         ),
            #         token=token,
            #         data=notification.data,
            #     )
            #     messaging.send(message)
            
            notification.mark_as_sent()
            logger.info(f"Push notification sent to user {notification.user.id}: {notification.title}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send push notification: {error_msg}")
            notification.mark_as_failed(error_msg)
            return False
    
    def send_bulk_notifications(
        self,
        users: List[User],
        title: str,
        message: str,
        category: str = 'general',
        priority: str = 'normal',
        data: Optional[Dict[str, Any]] = None,
        action_url: str = ''
    ) -> List['Notification']:
        """
        Send notifications to multiple users.
        
        Args:
            users: List of users to notify
            title: Notification title
            message: Notification message
            category: Category of notification
            priority: Priority level
            data: Additional data
            action_url: URL to navigate to
            
        Returns:
            List of created Notification instances
        """
        notifications = []
        for user in users:
            notification = self.send_notification(
                user=user,
                title=title,
                message=message,
                category=category,
                priority=priority,
                data=data,
                action_url=action_url
            )
            notifications.append(notification)
        return notifications
    
    def send_digest(
        self,
        user: User,
        digest_type: str = 'daily'
    ) -> Optional['NotificationDigest']:
        """
        Send a digest of unread notifications to a user.
        
        Args:
            user: The user to send digest to
            digest_type: Type of digest (hourly, daily, weekly)
            
        Returns:
            NotificationDigest instance if sent, None otherwise
        """
        from .models import Notification, NotificationDigest
        
        # Get unread notifications
        unread_notifications = Notification.objects.filter(
            user=user,
            is_read=False,
            notification_type=Notification.TYPE_IN_APP
        ).order_by('-created_at')[:50]
        
        if not unread_notifications.exists():
            logger.info(f"No unread notifications for user {user.id}, skipping digest")
            return None
        
        # Create digest
        notification_ids = list(unread_notifications.values_list('id', flat=True))
        digest = NotificationDigest.objects.create(
            user=user,
            digest_type=digest_type,
            notification_count=len(notification_ids),
            notification_ids=notification_ids
        )
        
        # Send digest email
        try:
            context = {
                'user': user,
                'notifications': unread_notifications[:20],
                'total_count': len(notification_ids),
                'digest_type': digest_type,
                'site_name': getattr(settings, 'SITE_NAME', 'LMS'),
                'site_url': getattr(settings, 'SITE_URL', ''),
            }
            
            subject = f"[{context['site_name']}] Your {digest_type} notification digest"
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@lms.com')
            
            # Plain text version
            text_content = f"You have {len(notification_ids)} unread notifications."
            
            # HTML version
            try:
                html_content = render_to_string('emails/digest.html', context)
            except:
                # Fallback
                html_content = f"""
                <html>
                <body>
                    <h2>Your {digest_type} Digest</h2>
                    <p>You have {len(notification_ids)} unread notifications.</p>
                    <ul>
                        {''.join([f'<li>{n.title}</li>' for n in unread_notifications[:10]])}
                    </ul>
                </body>
                </html>
                """
            
            # Send via enhanced EmailService
            result = self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                from_email=from_email,
                categories=['digest', digest_type]
            )
            
            if result.success:
                logger.info(f"Digest sent to {user.email} via {result.provider}: {len(notification_ids)} notifications")
                return digest
            else:
                logger.error(f"Failed to send digest: {result.error_message}")
                return None
            
        except Exception as e:
            logger.error(f"Failed to send digest: {str(e)}")
            return None
    
    def retry_failed_notifications(self, max_retries: int = 3) -> int:
        """
        Retry sending failed notifications.
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            Number of notifications successfully resent
        """
        from .models import Notification
        
        failed_notifications = Notification.objects.filter(
            status=Notification.STATUS_FAILED,
            retry_count__lt=max_retries
        )
        
        success_count = 0
        for notification in failed_notifications:
            notification.increment_retry()
            
            if notification.notification_type == Notification.TYPE_EMAIL:
                if self._send_email_notification(notification):
                    success_count += 1
            elif notification.notification_type == Notification.TYPE_IN_APP:
                if self._send_in_app_notification(notification):
                    success_count += 1
            elif notification.notification_type == Notification.TYPE_PUSH:
                if self._send_push_notification(notification):
                    success_count += 1
        
        logger.info(f"Retried {failed_notifications.count()} failed notifications, {success_count} succeeded")
        return success_count
    
    def mark_all_as_read(self, user: User) -> int:
        """
        Mark all notifications as read for a user.
        
        Args:
            user: The user whose notifications to mark as read
            
        Returns:
            Number of notifications marked as read
        """
        from .models import Notification
        
        unread_notifications = Notification.objects.filter(
            user=user,
            is_read=False
        )
        
        count = unread_notifications.count()
        for notification in unread_notifications:
            notification.mark_as_read()
        
        return count
    
    def get_unread_count(self, user: User) -> int:
        """
        Get the count of unread notifications for a user.
        
        Args:
            user: The user to get count for
            
        Returns:
            Number of unread notifications
        """
        from .models import Notification
        
        return Notification.objects.filter(
            user=user,
            is_read=False
        ).count()


class InAppNotificationService:
    """
    Service for managing in-app notifications and real-time delivery.
    """
    
    @staticmethod
    def get_user_notifications(
        user: User,
        is_read: Optional[bool] = None,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List['Notification']:
        """
        Get notifications for a user.
        
        Args:
            user: The user to get notifications for
            is_read: Filter by read status (None for all)
            category: Filter by category (None for all)
            limit: Maximum number of notifications to return
            
        Returns:
            List of Notification instances
        """
        from .models import Notification
        
        queryset = Notification.objects.filter(user=user)
        
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read)
        
        if category:
            queryset = queryset.filter(category=category)
        
        return list(queryset.order_by('-created_at')[:limit])
    
    @staticmethod
    def mark_as_read(notification_id: str, user: User) -> bool:
        """
        Mark a notification as read.
        
        Args:
            notification_id: ID of the notification
            user: The user who owns the notification
            
        Returns:
            True if successful, False otherwise
        """
        from .models import Notification
        
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
    
    @staticmethod
    def get_recent_notifications(user: User, minutes: int = 5) -> List['Notification']:
        """
        Get recent notifications for real-time polling.
        
        Args:
            user: The user to get notifications for
            minutes: Time window in minutes
            
        Returns:
            List of recent Notification instances
        """
        from .models import Notification
        
        since = timezone.now() - timedelta(minutes=minutes)
        
        return list(Notification.objects.filter(
            user=user,
            created_at__gte=since,
            is_read=False
        ).order_by('-created_at'))
