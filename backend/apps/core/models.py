"""
Core Abstract Models for Enterprise LMS
Provides base model classes with UUID primary keys, timestamps, and soft delete patterns.
"""

import uuid
from datetime import datetime
from typing import Optional

from django.db import models
from django.contrib.auth import get_user_model


class UUIDModel(models.Model):
    """
    Abstract base model with UUID primary key.
    All models in the LMS should inherit from this or its subclasses.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="Unique identifier for this record"
    )

    class Meta:
        abstract = True


class TimestampedModel(UUIDModel):
    """
    Abstract base model with UUID primary key and automatic timestamp fields.
    Provides created_at and updated_at fields that are automatically managed.
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when this record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        help_text="Timestamp when this record was last updated"
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']


class AuditedModel(TimestampedModel):
    """
    Abstract base model with audit fields for tracking who created/modified records.
    Extends TimestampedModel with created_by and updated_by foreign keys.
    """
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        help_text="User who created this record"
    )
    updated_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
        help_text="User who last updated this record"
    )

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    """
    Custom manager that excludes soft-deleted records by default.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteAllManager(models.Manager):
    """
    Custom manager that includes all records including soft-deleted ones.
    """
    def get_queryset(self):
        return super().get_queryset()


class SoftDeleteModel(TimestampedModel):
    """
    Abstract base model with soft delete capability.
    Records are marked as deleted rather than physically removed.
    Provides is_deleted and deleted_at fields.
    """
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag indicating if this record has been soft deleted"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp when this record was soft deleted"
    )
    deleted_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_deleted',
        help_text="User who soft deleted this record"
    )

    # Default manager excludes soft-deleted records
    objects = SoftDeleteManager()
    # All manager includes soft-deleted records
    all_objects = SoftDeleteAllManager()

    class Meta:
        abstract = True

    def soft_delete(self, deleted_by: Optional['User'] = None) -> None:
        """
        Soft delete this record by setting is_deleted=True and deleted_at=now.
        
        Args:
            deleted_by: Optional user who performed the deletion
        """
        self.is_deleted = True
        self.deleted_at = datetime.now()
        self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])

    def restore(self) -> None:
        """
        Restore a soft-deleted record by clearing deletion flags.
        """
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])

    def hard_delete(self) -> None:
        """
        Permanently delete this record from the database.
        Use with caution - this operation cannot be undone.
        """
        super().delete()


class BaseModel(SoftDeleteModel, AuditedModel):
    """
    Complete abstract base model combining all features:
    - UUID primary key
    - Timestamps (created_at, updated_at)
    - Audit fields (created_by, updated_by)
    - Soft delete (is_deleted, deleted_at, deleted_by)
    
    This is the recommended base class for most models in the LMS.
    """
    class Meta:
        abstract = True
        ordering = ['-created_at']


class MetadataModel(models.Model):
    """
    Abstract model for storing flexible metadata as JSON.
    Useful for extensible schemas where additional fields may vary.
    """
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional flexible metadata stored as JSON"
    )

    class Meta:
        abstract = True

    def get_metadata(self, key: str, default=None):
        """
        Get a value from the metadata dictionary.
        
        Args:
            key: The metadata key to retrieve
            default: Default value if key not found
            
        Returns:
            The metadata value or default
        """
        return self.metadata.get(key, default)

    def set_metadata(self, key: str, value) -> None:
        """
        Set a value in the metadata dictionary.
        
        Args:
            key: The metadata key to set
            value: The value to store
        """
        if self.metadata is None:
            self.metadata = {}
        self.metadata[key] = value
        self.save(update_fields=['metadata'])


class StatusModel(models.Model):
    """
    Abstract model for entities with a status field and status transitions.
    """
    STATUS_CHOICES = []
    
    status = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Current status of this record"
    )
    status_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when status was last changed"
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Override save to track status changes.
        """
        if self.pk:
            try:
                old_instance = self.__class__.all_objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    self.status_changed_at = datetime.now()
            except self.__class__.DoesNotExist:
                pass
        super().save(*args, **kwargs)
