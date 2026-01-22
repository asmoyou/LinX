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

export const submitGoalSchema = z.object({
  title: z.string()
    .min(5, 'Goal title must be at least 5 characters')
    .max(100, 'Goal title must not exceed 100 characters'),
  description: z.string()
    .min(10, 'Goal description must be at least 10 characters')
    .max(2000, 'Goal description must not exceed 2000 characters'),
  priority: z.enum(['low', 'medium', 'high']).optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;
export type RegisterFormData = z.infer<typeof registerSchema>;
export type CreateAgentFormData = z.infer<typeof createAgentSchema>;
export type SubmitGoalFormData = z.infer<typeof submitGoalSchema>;
