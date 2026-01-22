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

export const uploadDocumentSchema = z.object({
  title: z.string()
    .min(3, 'Document title must be at least 3 characters')
    .max(100, 'Document title must not exceed 100 characters'),
  description: z.string().max(500, 'Description must not exceed 500 characters').optional(),
  tags: z.string().optional(),
  visibility: z.enum(['private', 'team', 'public']).default('private'),
});

export const editProfileSchema = z.object({
  username: z.string()
    .min(3, 'Username must be at least 3 characters')
    .max(30, 'Username must not exceed 30 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Username can only contain letters, numbers, underscores and hyphens'),
  email: z.string().email('Invalid email address'),
  fullName: z.string().max(50, 'Full name must not exceed 50 characters').optional(),
  bio: z.string().max(200, 'Bio must not exceed 200 characters').optional(),
});

export const createSkillSchema = z.object({
  name: z.string()
    .min(3, 'Skill name must be at least 3 characters')
    .max(50, 'Skill name must not exceed 50 characters')
    .regex(/^[a-zA-Z0-9\s_-]+$/, 'Skill name can only contain letters, numbers, spaces, underscores and hyphens'),
  description: z.string()
    .min(10, 'Description must be at least 10 characters')
    .max(500, 'Description must not exceed 500 characters'),
  category: z.enum(['data', 'content', 'code', 'research', 'other']),
  difficulty: z.enum(['beginner', 'intermediate', 'advanced']),
  parameters: z.string().optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;
export type RegisterFormData = z.infer<typeof registerSchema>;
export type CreateAgentFormData = z.infer<typeof createAgentSchema>;
export type SubmitGoalFormData = z.infer<typeof submitGoalSchema>;
export type UploadDocumentFormData = z.infer<typeof uploadDocumentSchema>;
export type EditProfileFormData = z.infer<typeof editProfileSchema>;
export type CreateSkillFormData = z.infer<typeof createSkillSchema>;
