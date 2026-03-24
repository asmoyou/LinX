import { useEffect } from "react";
import { useAuthStore } from "../stores/authStore";
import { useUserStore } from "../stores/userStore";
import { useAgentStore } from "../stores/agentStore";
import { useTaskStore } from "../stores/taskStore";
import { useKnowledgeStore } from "../stores/knowledgeStore";
import { useMemoryWorkbenchStore } from "../stores/memoryWorkbenchStore";
import apiClient from "../api/client";
import { memoryWorkbenchApi } from "../api/memoryWorkbench";

/**
 * Hook to sync stores with backend API on mount
 *
 * This hook fetches initial data from the backend and populates
 * the stores when the component mounts. It should be used at the
 * app root level.
 *
 * @param options - Configuration options
 */
export const useStoreSync = (
  options: {
    syncUser?: boolean;
    syncAgents?: boolean;
    syncTasks?: boolean;
    syncKnowledge?: boolean;
    syncMemories?: boolean;
  } = {},
) => {
  const {
    syncUser = true,
    syncAgents = true,
    syncTasks = false,
    syncKnowledge = true,
    syncMemories = true,
  } = options;

  const { isAuthenticated, token } = useAuthStore();
  const userStore = useUserStore();
  const agentStore = useAgentStore();
  const taskStore = useTaskStore();
  const knowledgeStore = useKnowledgeStore();
  const memoryWorkbenchStore = useMemoryWorkbenchStore();

  useEffect(() => {
    if (!isAuthenticated || !token) {
      return;
    }

    const fetchData = async () => {
      try {
        // Fetch user profile and quotas
        if (syncUser) {
          userStore.setLoading(true);
          try {
            const [profileResponse, quotasResponse] = await Promise.all([
              apiClient.get("/users/me"),
              apiClient.get("/users/me/quotas"),
            ]);
            userStore.setProfile(profileResponse.data);
            userStore.setQuotas(quotasResponse.data);
          } catch (error) {
            console.error("Failed to fetch user data:", error);
            userStore.setError("Failed to load user profile");
          } finally {
            userStore.setLoading(false);
          }
        }

        // Fetch agents
        if (syncAgents) {
          agentStore.setLoading(true);
          try {
            const response = await apiClient.get("/agents");
            agentStore.setAgents(response.data);
          } catch (error) {
            console.error("Failed to fetch agents:", error);
            agentStore.setError("Failed to load agents");
          } finally {
            agentStore.setLoading(false);
          }
        }

        // Fetch tasks and goals
        if (syncTasks) {
          taskStore.setLoading(true);
          try {
            // Legacy /goals and /tasks APIs are deprecated.
            // Mission orchestration data is handled by missionStore.
            taskStore.setGoals([]);
            taskStore.setTasks([]);
          } catch (error) {
            console.error("Failed to fetch tasks:", error);
            taskStore.setError("Failed to load tasks");
          } finally {
            taskStore.setLoading(false);
          }
        }

        // Fetch knowledge base documents
        if (syncKnowledge) {
          knowledgeStore.setLoading(true);
          try {
            const response = await apiClient.get("/knowledge");
            knowledgeStore.setDocuments(response.data);
          } catch (error) {
            console.error("Failed to fetch knowledge:", error);
            knowledgeStore.setError("Failed to load documents");
          } finally {
            knowledgeStore.setLoading(false);
          }
        }

        // Fetch memories
        if (syncMemories) {
          memoryWorkbenchStore.setLoading(true);
          try {
            const userMemory = await memoryWorkbenchApi.listUserMemory({
              limit: 100,
            });
            memoryWorkbenchStore.setRecords(userMemory.items);
          } catch (error) {
            console.error("Failed to fetch memories:", error);
            memoryWorkbenchStore.setError("Failed to load memories");
          } finally {
            memoryWorkbenchStore.setLoading(false);
          }
        }
      } catch (error) {
        console.error("Failed to sync stores:", error);
      }
    };

    fetchData();
  }, [
    isAuthenticated,
    token,
    syncUser,
    syncAgents,
    syncTasks,
    syncKnowledge,
    syncMemories,
  ]);
};

/**
 * Hook to sync a specific store with the backend
 * Useful for refreshing data on demand
 */
export const useRefreshStore = () => {
  const refreshUser = async () => {
    const userStore = useUserStore.getState();
    userStore.setLoading(true);
    try {
      const [profileResponse, quotasResponse] = await Promise.all([
        apiClient.get("/users/me"),
        apiClient.get("/users/me/quotas"),
      ]);
      userStore.setProfile(profileResponse.data);
      userStore.setQuotas(quotasResponse.data);
    } catch (error) {
      console.error("Failed to refresh user data:", error);
      userStore.setError("Failed to refresh user profile");
    } finally {
      userStore.setLoading(false);
    }
  };

  const refreshAgents = async () => {
    const agentStore = useAgentStore.getState();
    agentStore.setLoading(true);
    try {
      const response = await apiClient.get("/agents");
      agentStore.setAgents(response.data);
    } catch (error) {
      console.error("Failed to refresh agents:", error);
      agentStore.setError("Failed to refresh agents");
    } finally {
      agentStore.setLoading(false);
    }
  };

  const refreshTasks = async () => {
    const taskStore = useTaskStore.getState();
    taskStore.setLoading(true);
    try {
      // Legacy /goals and /tasks APIs are deprecated.
      taskStore.setGoals([]);
      taskStore.setTasks([]);
    } catch (error) {
      console.error("Failed to refresh tasks:", error);
      taskStore.setError("Failed to refresh tasks");
    } finally {
      taskStore.setLoading(false);
    }
  };

  const refreshKnowledge = async () => {
    const knowledgeStore = useKnowledgeStore.getState();
    knowledgeStore.setLoading(true);
    try {
      const response = await apiClient.get("/knowledge");
      knowledgeStore.setDocuments(response.data);
    } catch (error) {
      console.error("Failed to refresh knowledge:", error);
      knowledgeStore.setError("Failed to refresh documents");
    } finally {
      knowledgeStore.setLoading(false);
    }
  };

  const refreshMemories = async () => {
    const memoryWorkbenchStore = useMemoryWorkbenchStore.getState();
    memoryWorkbenchStore.setLoading(true);
    try {
      const userMemory = await memoryWorkbenchApi.listUserMemory({
        limit: 100,
      });
      memoryWorkbenchStore.setRecords(userMemory.items);
    } catch (error) {
      console.error("Failed to refresh memories:", error);
      memoryWorkbenchStore.setError("Failed to refresh memories");
    } finally {
      memoryWorkbenchStore.setLoading(false);
    }
  };

  return {
    refreshUser,
    refreshAgents,
    refreshTasks,
    refreshKnowledge,
    refreshMemories,
  };
};
