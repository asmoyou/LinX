/**
 * MCP Servers API client
 */

import apiClient from "./client";

export interface McpServer {
  server_id: string;
  name: string;
  description?: string | null;
  transport_type: "stdio" | "sse" | "streamable_http";
  command?: string | null;
  args?: string[] | null;
  url?: string | null;
  headers?: Record<string, string> | null;
  env_vars?: Record<string, string> | null;
  status: "connected" | "disconnected" | "error" | "syncing";
  tool_count: number;
  last_connected_at?: string | null;
  last_sync_at?: string | null;
  error_message?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateMcpServerRequest {
  name: string;
  description?: string;
  transport_type: "stdio" | "sse" | "streamable_http";
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, string>;
  env_vars?: Record<string, string>;
}

export interface UpdateMcpServerRequest {
  name?: string;
  description?: string;
  transport_type?: "stdio" | "sse" | "streamable_http";
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, string>;
  env_vars?: Record<string, string>;
  is_active?: boolean;
}

export interface SyncResult {
  added: number;
  updated: number;
  removed: number;
  total_tools: number;
  errors: string[];
}

export interface ConnectionTestResult {
  connected: boolean;
  tool_count: number;
  error?: string | null;
}

export interface McpServerTool {
  skill_id: string;
  skill_slug: string;
  display_name: string;
  description: string;
  is_active: boolean;
  interface_definition: Record<string, unknown>;
  execution_count: number;
}

export const mcpServersApi = {
  async getAll(activeOnly = true): Promise<McpServer[]> {
    const resp = await apiClient.get("/mcp-servers", {
      params: { active_only: activeOnly },
    });
    return resp.data;
  },

  async create(data: CreateMcpServerRequest): Promise<McpServer> {
    const resp = await apiClient.post("/mcp-servers", data);
    return resp.data;
  },

  async getById(serverId: string): Promise<McpServer> {
    const resp = await apiClient.get(`/mcp-servers/${serverId}`);
    return resp.data;
  },

  async update(
    serverId: string,
    data: UpdateMcpServerRequest,
  ): Promise<McpServer> {
    const resp = await apiClient.put(`/mcp-servers/${serverId}`, data);
    return resp.data;
  },

  async delete(serverId: string): Promise<void> {
    await apiClient.delete(`/mcp-servers/${serverId}`);
  },

  async testConnection(serverId: string): Promise<ConnectionTestResult> {
    const resp = await apiClient.post(`/mcp-servers/${serverId}/connect`);
    return resp.data;
  },

  async syncTools(serverId: string): Promise<SyncResult> {
    const resp = await apiClient.post(`/mcp-servers/${serverId}/sync`);
    return resp.data;
  },

  async getTools(serverId: string): Promise<McpServerTool[]> {
    const resp = await apiClient.get(`/mcp-servers/${serverId}/tools`);
    return resp.data;
  },

  async disconnect(serverId: string): Promise<void> {
    await apiClient.post(`/mcp-servers/${serverId}/disconnect`);
  },
};
