import { z } from 'zod';

// Common validation patterns
const passwordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
const nameRegex = /^[a-zA-Z\s'-]+$/;

// Login form validation schema
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
  password: z
    .string()
    .min(1, 'Password is required')
    .min(8, 'Password must be at least 8 characters'),
  rememberMe: z.boolean().optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;

// Registration form validation schema
export const registerSchema = z
  .object({
    firstName: z
      .string()
      .min(1, 'First name is required')
      .min(2, 'First name must be at least 2 characters')
      .max(50, 'First name must be less than 50 characters')
      .regex(nameRegex, 'First name can only contain letters, spaces, hyphens, and apostrophes'),
    lastName: z
      .string()
      .min(1, 'Last name is required')
      .min(2, 'Last name must be at least 2 characters')
      .max(50, 'Last name must be less than 50 characters')
      .regex(nameRegex, 'Last name can only contain letters, spaces, hyphens, and apostrophes'),
    email: z
      .string()
      .min(1, 'Email is required')
      .email('Please enter a valid email address'),
    password: z
      .string()
      .min(1, 'Password is required')
      .min(8, 'Password must be at least 8 characters')
      .regex(
        passwordRegex,
        'Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character'
      ),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
    acceptTerms: z.boolean().refine((val) => val === true, {
      message: 'You must accept the terms and conditions',
    }),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  });

export type RegisterFormData = z.infer<typeof registerSchema>;

// Password reset request schema
export const forgotPasswordSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
});

export type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;

// Password reset confirmation schema
export const resetPasswordSchema = z
  .object({
    token: z.string().min(1, 'Reset token is required'),
    password: z
      .string()
      .min(1, 'Password is required')
      .min(8, 'Password must be at least 8 characters')
      .regex(
        passwordRegex,
        'Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character'
      ),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  });

export type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;

// Email verification schema
export const verifyEmailSchema = z.object({
  token: z.string().min(1, 'Verification token is required'),
});

export type VerifyEmailFormData = z.infer<typeof verifyEmailSchema>;

// Resend verification email schema
export const resendVerificationSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
});

export type ResendVerificationFormData = z.infer<typeof resendVerificationSchema>;

// Course search/filter schema
export const courseFilterSchema = z.object({
  search: z.string().optional(),
  category: z.string().optional(),
  level: z.enum(['beginner', 'intermediate', 'advanced']).optional(),
  sortBy: z.enum(['newest', 'popular', 'rating', 'price_asc', 'price_desc']).optional(),
  page: z.number().int().min(1).optional(),
  pageSize: z.number().int().min(1).max(100).optional(),
});

export type CourseFilterData = z.infer<typeof courseFilterSchema>;

// Profile update schema
export const profileUpdateSchema = z.object({
  firstName: z
    .string()
    .min(2, 'First name must be at least 2 characters')
    .max(50, 'First name must be less than 50 characters')
    .regex(nameRegex, 'First name can only contain letters, spaces, hyphens, and apostrophes')
    .optional(),
  lastName: z
    .string()
    .min(2, 'Last name must be at least 2 characters')
    .max(50, 'Last name must be less than 50 characters')
    .regex(nameRegex, 'Last name can only contain letters, spaces, hyphens, and apostrophes')
    .optional(),
  bio: z.string().max(500, 'Bio must be less than 500 characters').optional(),
  phoneNumber: z
    .string()
    .regex(/^\+?[\d\s-()]+$/, 'Please enter a valid phone number')
    .optional(),
});

export type ProfileUpdateFormData = z.infer<typeof profileUpdateSchema>;

// Password change schema
export const passwordChangeSchema = z
  .object({
    currentPassword: z.string().min(1, 'Current password is required'),
    newPassword: z
      .string()
      .min(1, 'New password is required')
      .min(8, 'Password must be at least 8 characters')
      .regex(
        passwordRegex,
        'Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character'
      ),
    confirmNewPassword: z.string().min(1, 'Please confirm your new password'),
  })
  .refine((data) => data.newPassword === data.confirmNewPassword, {
    message: 'Passwords do not match',
    path: ['confirmNewPassword'],
  });

export type PasswordChangeFormData = z.infer<typeof passwordChangeSchema>;

// Helper function to get field error message
export const getFieldError = (
  errors: Record<string, string[]> | undefined,
  field: string
): string | undefined => {
  return errors?.[field]?.[0];
};

// Helper to format Zod errors into field_errors format
export const formatZodErrors = (
  error: z.ZodError
): Record<string, string[]> => {
  const fieldErrors: Record<string, string[]> = {};
  error.errors.forEach((err) => {
    const path = err.path.join('.');
    if (!fieldErrors[path]) {
      fieldErrors[path] = [];
    }
    fieldErrors[path].push(err.message);
  });
  return fieldErrors;
};
