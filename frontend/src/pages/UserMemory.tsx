import React from "react";
import { useTranslation } from "react-i18next";
import { MemoryWorkbench } from "@/components/memory/MemoryWorkbench";

export const UserMemory: React.FC = () => {
  const { t } = useTranslation();

  return (
    <MemoryWorkbench
      title={t("memory.title", { defaultValue: "Memory System" })}
      description={t("memory.description.userMemory", {
        defaultValue:
          "Long-term user facts including relationships, experiences, preferences, goals, and important events.",
      })}
    />
  );
};
