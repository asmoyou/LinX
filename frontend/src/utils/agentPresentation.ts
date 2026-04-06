import type { Agent } from "@/types/agent";

export const isExternalRuntime = (runtimeType?: string | null): boolean =>
  typeof runtimeType === "string" && runtimeType.startsWith("external") || runtimeType === "remote_session";

export const getAgentKind = (agent: Pick<Agent, "runtimeType">): "internal" | "external" =>
  isExternalRuntime(agent.runtimeType) ? "external" : "internal";

export const getAgentTypeToken = (agent: Pick<Agent, "runtimeType" | "type">): string => {
  const kind = getAgentKind(agent);
  if (kind === "external") return "external_general";
  return "internal_general";
};
