import React from 'react';
import { Navigate } from 'react-router-dom';

export const MemoryRedirectPage: React.FC = () => <Navigate to="/memory/user-memory" replace />;
