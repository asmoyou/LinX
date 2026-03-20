import { describe, expect, it } from 'vitest';
import type { ConversationMessage } from '@/types/agent';
import {
  derivePersistentProcessDescriptor,
  derivePersistentArtifacts,
  derivePersistentScheduleEvents,
  getPersistentFallbackAssistantText,
  mapChunkToPersistentPhase,
  shouldHideProcessLine,
} from '@/components/workforce/persistent/persistentConversationHelpers';

const baseMessage: ConversationMessage = {
  id: 'message-1',
  conversationId: 'conversation-1',
  role: 'assistant',
  contentText: '',
  contentJson: null,
  attachments: [],
  source: 'web',
  createdAt: '2025-01-01T00:00:00Z',
};

describe('persistentConversationHelpers', () => {
  it('maps streaming chunks into compact persistent phases', () => {
    expect(mapChunkToPersistentPhase({ type: 'runtime' })).toBe('thinking');
    expect(mapChunkToPersistentPhase({ type: 'tool_call' })).toBe(
      'using_tools',
    );
    expect(mapChunkToPersistentPhase({ type: 'tool_result' })).toBe(
      'finalizing',
    );
    expect(mapChunkToPersistentPhase({ type: 'retry_attempt' })).toBe(
      'recovering',
    );
    expect(mapChunkToPersistentPhase({ type: 'content' })).toBeNull();
    expect(mapChunkToPersistentPhase({ type: 'done' })).toBeNull();
  });

  it('hides the process line permanently after final content starts', () => {
    expect(shouldHideProcessLine(false)).toBe(false);
    expect(shouldHideProcessLine(true)).toBe(true);
  });

  it('prefers visible artifact delta files over broad workspace snapshots', () => {
    const message: ConversationMessage = {
      ...baseMessage,
      contentText:
        '最终结果保存在 /workspace/output/final.md，并补充了 ./notes.txt',
      contentJson: {
        artifactDelta: [
          {
            path: '/workspace/output/report.csv',
            name: 'report.csv',
          },
          {
            path: '/workspace/.linux_runtime/python_deps/site-packages.txt',
            name: 'site-packages.txt',
          },
          {
            path: '/workspace/pip_cache/http/index.json',
            name: 'index.json',
          },
        ],
        rounds: [
          {
            content: 'wrote /workspace/output/chart.png',
          },
          {
            content: 'appended to ./notes.txt',
            artifacts: [{ path: '/workspace/output/report.csv' }],
          },
        ],
      },
    };

    expect(derivePersistentArtifacts(message)).toEqual([
      {
        path: '/workspace/output/report.csv',
        name: 'report.csv',
      },
    ]);
  });

  it('does not surface stale workspace files for ordinary text-only replies', () => {
    const message: ConversationMessage = {
      ...baseMessage,
      contentText: '您好！看到您发了个问号，是有什么需要我帮忙的吗？',
      contentJson: {
        artifacts: [
          {
            path: 'output/Xiao_Luoxi_Case_Progress_Report_EN.md',
            name: 'Xiao_Luoxi_Case_Progress_Report_EN.md',
          },
          {
            path: 'output/小若希事件进展报告.md',
            name: '小若希事件进展报告.md',
          },
        ],
        artifactDelta: [],
      },
    };

    expect(derivePersistentArtifacts(message)).toEqual([]);
  });

  it('derives richer one-line process descriptors for retrieval and tool chunks', () => {
    expect(
      derivePersistentProcessDescriptor({
        type: 'info',
        content: '[记忆检索][skills] 命中 2 条',
      }),
    ).toEqual({
      phase: 'thinking',
      kind: 'memory',
      detail: '命中 2 条',
      accent: 'skills',
    });

    expect(
      derivePersistentProcessDescriptor({
        type: 'info',
        content: '[知识库检索] 命中 3 条',
      }),
    ).toEqual({
      phase: 'thinking',
      kind: 'knowledge',
      detail: '命中 3 条',
      accent: null,
    });

    expect(
      derivePersistentProcessDescriptor({
        type: 'tool_call',
        content:
          '🔧 **调用工具: bash** 参数摘要: command=npm run build, workdir=/workspace',
      }),
    ).toEqual({
      phase: 'using_tools',
      kind: 'tool',
      detail: 'npm run build',
      accent: 'bash',
    });
  });

  it('merges schedule events from legacy rounds and top-level content json', () => {
    const message: ConversationMessage = {
      ...baseMessage,
      contentJson: {
        rounds: [
          {
            scheduleEvents: [
              {
                schedule_id: 'schedule-1',
                agent_id: 'agent-1',
                name: '日报提醒',
                status: 'active',
                next_run_at: '2025-01-02T01:00:00+00:00',
                timezone: 'Asia/Shanghai',
                created_via: 'agent_auto',
                bound_conversation_id: 'conversation-1',
                origin_surface: 'persistent_chat',
              },
            ],
          },
        ],
        scheduleEvents: [
          {
            schedule_id: 'schedule-2',
            agent_id: 'agent-1',
            name: '周报提醒',
            status: 'active',
            next_run_at: '2025-01-03T01:00:00+00:00',
            timezone: 'Asia/Shanghai',
            created_via: 'agent_auto',
            bound_conversation_id: 'conversation-1',
            origin_surface: 'persistent_chat',
          },
          {
            schedule_id: 'schedule-1',
            agent_id: 'agent-1',
            name: '日报提醒',
            status: 'active',
            next_run_at: '2025-01-02T01:00:00+00:00',
            timezone: 'Asia/Shanghai',
            created_via: 'agent_auto',
            bound_conversation_id: 'conversation-1',
            origin_surface: 'persistent_chat',
          },
        ],
      },
    };

    expect(derivePersistentScheduleEvents(message).map((item) => item.name)).toEqual([
      '日报提醒',
      '周报提醒',
    ]);
  });

  it('uses fallback assistant text only when structured results exist without final prose', () => {
    expect(
      getPersistentFallbackAssistantText(
        {
          ...baseMessage,
          contentText: '最终答案',
        },
        '已生成结果',
      ),
    ).toBe('最终答案');

    expect(
      getPersistentFallbackAssistantText(
        {
          ...baseMessage,
          contentJson: {
            artifacts: [{ path: '/workspace/output/report.csv' }],
          },
        },
        '已生成结果',
      ),
    ).toBe('已生成结果');

    expect(
      getPersistentFallbackAssistantText(baseMessage, '已生成结果'),
    ).toBe('');
  });
});
