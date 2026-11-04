"""
Tests for Notifications app
Covers Notification model, services, and API endpoints.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.notifications.models import Notification, NotificationPreference, NotificationDigest
from apps.notifications.services import NotificationService, EmailService, InAppNotificationService

User = get_user_model()


class NotificationModelTests(TestCase):
    """Tests for Notification model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_notification_creation(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=self.user,
            notification_type=Notification.TYPE_IN_APP,
            category=Notification.CATEGORY_GENERAL,
            title='Test Notification',
            message='This is a test message',
            data={'key': 'value'}
        )
        
        self.assertEqual(notification.title, 'Test Notification')
        self.assertEqual(notification.message, 'This is a test message')
        self.assertEqual(notification.status, Notification.STATUS_PENDING)
        self.assertFalse(notification.is_read)
    
    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.user,
            title='Test',
            message='Test message'
        )
        
        notification.mark_as_read()
        
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(notification.status, Notification.STATUS_READ)
    
    def test_mark_as_sent(self):
        """Test marking notification as sent."""
        notification = Notification.objects.create(
            user=self.user,
            title='Test',
            message='Test message'
        )
        
        notification.mark_as_sent()
        
        self.assertEqual(notification.status, Notification.STATUS_SENT)
        self.assertIsNotNone(notification.sent_at)
    
    def test_mark_as_failed(self):
        """Test marking notification as failed."""
        notification = Notification.objects.create(
            user=self.user,
            title='Test',
            message='Test message'
        )
        
        notification.mark_as_failed('SMTP error')
        
        self.assertEqual(notification.status, Notification.STATUS_FAILED)
        self.assertEqual(notification.error_message, 'SMTP error')
    
    def test_increment_retry(self):
        """Test incrementing retry count."""
        notification = Notification.objects.create(
            user=self.user,
            title='Test',
            message='Test message'
        )
        
        notification.increment_retry()
        
        self.assertEqual(notification.retry_count, 1)


class NotificationPreferenceModelTests(TestCase):
    """Tests for NotificationPreference model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_preference_creation(self):
        """Test creating notification preferences."""
        preference = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            in_app_enabled=True
        )
        
        self.assertTrue(preference.email_enabled)
        self.assertTrue(preference.in_app_enabled)
        self.assertFalse(preference.push_enabled)
    
    def test_should_send_email(self):
        """Test email sending check."""
        preference = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            notify_on_course_updates=True
        )
        
        self.assertTrue(preference.should_send_email(Notification.CATEGORY_COURSE))
    
    def test_should_not_send_email_when_disabled(self):
        """Test email not sent when disabled."""
        preference = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=False
        )
        
        self.assertFalse(preference.should_send_email())


class NotificationServiceTests(TestCase):
    """Tests for NotificationService."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.service = NotificationService()
    
    @patch('apps.notifications.services.EmailMultiAlternatives')
    def test_send_email_notification(self, mock_email_class):
        """Test sending email notification."""
        mock_email = MagicMock()
        mock_email_class.return_value = mock_email
        
        notification = Notification.objects.create(
            user=self.user,
            notification_type=Notification.TYPE_EMAIL,
            title='Test Email',
            message='Test message'
        )
        
        result = self.service._send_email_notification(notification)
        
        self.assertTrue(result)
        mock_email.send.assert_called_once()
    
    def test_send_in_app_notification(self):
        """Test sending in-app notification."""
        notification = Notification.objects.create(
            user=self.user,
            notification_type=Notification.TYPE_IN_APP,
            title='Test',
            message='Test message'
        )
        
        result = self.service._send_in_app_notification(notification)
        
        self.assertTrue(result)
        self.assertEqual(notification.status, Notification.STATUS_DELIVERED)
    
    def test_get_unread_count(self):
        """Test getting unread count."""
        Notification.objects.create(user=self.user, title='Unread', message='Test')
        Notification.objects.create(user=self.user, title='Read', message='Test', is_read=True)
        
        count = self.service.get_unread_count(self.user)
        
        self.assertEqual(count, 1)
    
    def test_mark_all_as_read(self):
        """Test marking all notifications as read."""
        Notification.objects.create(user=self.user, title='Unread1', message='Test')
        Notification.objects.create(user=self.user, title='Unread2', message='Test')
        
        count = self.service.mark_all_as_read(self.user)
        
        self.assertEqual(count, 2)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=True).count(), 2)


class NotificationAPITests(APITestCase):
    """Tests for Notification API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_list_notifications(self):
        """Test listing notifications."""
        Notification.objects.create(user=self.user, title='Test', message='Test')
        
        response = self.client.get('/api/v1/notifications/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_unread_count(self):
        """Test getting unread count."""
        Notification.objects.create(user=self.user, title='Test', message='Test')
        
        response = self.client.get('/api/v1/notifications/unread-count/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 1)
    
    def test_mark_read(self):
        """Test marking notifications as read."""
        notification = Notification.objects.create(user=self.user, title='Test', message='Test')
        
        response = self.client.post('/api/v1/notifications/mark-read/', {
            'notification_ids': [str(notification.id)]
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
    
    def test_mark_all_read(self):
        """Test marking all notifications as read."""
        Notification.objects.create(user=self.user, title='Test1', message='Test')
        Notification.objects.create(user=self.user, title='Test2', message='Test')
        
        response = self.client.post('/api/v1/notifications/mark-read/', {
            'mark_all': True
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=True).count(), 2)
    
    def test_get_preferences(self):
        """Test getting notification preferences."""
        response = self.client.get('/api/v1/notifications/preferences/my/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('email_enabled', response.data)
    
    def test_update_preferences(self):
        """Test updating notification preferences."""
        response = self.client.patch('/api/v1/notifications/preferences/my/', {
            'email_enabled': False
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['email_enabled'])


class EmailServiceTests(TestCase):
    """Tests for EmailService."""
    
    @patch('apps.notifications.services.EmailMultiAlternatives')
    def test_send_email(self, mock_email_class):
        """Test sending email."""
        mock_email = MagicMock()
        mock_email_class.return_value = mock_email
        
        result = EmailService.send_email(
            to_email='test@example.com',
            subject='Test Subject',
            text_content='Test content'
        )
        
        self.assertTrue(result)
        mock_email.send.assert_called_once()
    
    @patch('apps.notifications.services.render_to_string')
    @patch('apps.notifications.services.EmailMultiAlternatives')
    def test_send_template_email(self, mock_email_class, mock_render):
        """Test sending template email."""
        mock_email = MagicMock()
        mock_email_class.return_value = mock_email
        mock_render.return_value = 'Rendered content'
        
        result = EmailService.send_template_email(
            to_email='test@example.com',
            subject='Test',
            template_name='notification',
            context={'key': 'value'}
        )
        
        self.assertTrue(result)
        mock_render.assert_called()


class InAppNotificationServiceTests(TestCase):
    """Tests for InAppNotificationService."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='testpass123'
        )
    
    def test_get_user_notifications(self):
        """Test getting user notifications."""
        Notification.objects.create(user=self.user, title='Test', message='Test')
        
        notifications = InAppNotificationService.get_user_notifications(self.user)
        
        self.assertEqual(len(notifications), 1)
    
    def test_get_user_notifications_filtered(self):
        """Test getting filtered notifications."""
        Notification.objects.create(user=self.user, title='Unread', message='Test', is_read=False)
        Notification.objects.create(user=self.user, title='Read', message='Test', is_read=True)
        
        unread = InAppNotificationService.get_user_notifications(self.user, is_read=False)
        read = InAppNotificationService.get_user_notifications(self.user, is_read=True)
        
        self.assertEqual(len(unread), 1)
        self.assertEqual(len(read), 1)
    
    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(user=self.user, title='Test', message='Test')
        
        result = InAppNotificationService.mark_as_read(str(notification.id), self.user)
        
        self.assertTrue(result)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
    
    def test_get_recent_notifications(self):
        """Test getting recent notifications."""
        Notification.objects.create(user=self.user, title='Recent', message='Test')
        
        notifications = InAppNotificationService.get_recent_notifications(self.user, minutes=5)
        
        self.assertEqual(len(notifications), 1)
