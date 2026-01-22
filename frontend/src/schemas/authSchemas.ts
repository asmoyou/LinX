import { z } from 'zod';

export const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

export const registerSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  email: z.string().email('Invalid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
  confirmPassword: z.string().min(1, 'Please confirm your password'),
}).refine((data) => data.password === data.confirmPassword, {
  message: 'Passwords do not match',
  path: ['confirmPassword'],
});

export const createAgentSchema = z.object({
  name: z.string()
    .min(3, 'Agent name must be at least 3 characters')
    .max(50, 'Agent name must not exceed 50 characters')
    .regex(/^[a-zA-Z0-9\s_-]+$/, 'Agent name can only contain letters, numbers, spaces, underscores and hyphens'),
  template: z.string().min(1, 'Please select a template'),
  description: z.string().max(200, 'Description must not exceed 200 characters').optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;
export type RegisterFormData = z.infer<typeof registerSchema>;
export type CreateAgentFormData = z.infer<typeof createAgentSchema>;
