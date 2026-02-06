import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Building2,
  Plus,
  Search,
  Users,
  Bot,
  Database,
  Edit2,
  Trash2,
  ChevronRight,
  ChevronDown,
  X,
  FolderTree,
  List,
} from 'lucide-react';
import { useAuthStore } from '@/stores';
import { departmentsApi } from '@/api/departments';
import toast from 'react-hot-toast';
import type {
  Department,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
} from '@/types/department';

// ─── Department Form Dialog ─────────────────────────────────────────────────

interface DepartmentFormProps {
  department?: Department;
  onClose: () => void;
  onSaved: () => void;
}

const DepartmentForm: React.FC<DepartmentFormProps> = ({ department, onClose, onSaved }) => {
  const { t } = useTranslation();
  const [allDepartments, setAllDepartments] = useState<Department[]>([]);
  const isEditing = !!department;

  const [name, setName] = useState(department?.name || '');
  const [code, setCode] = useState(department?.code || '');
  const [description, setDescription] = useState(department?.description || '');
  const [parentId, setParentId] = useState(department?.parentId || '');
  const [sortOrder, setSortOrder] = useState(department?.sortOrder || 0);
  const [status, setStatus] = useState(department?.status || 'active');
  const [saving, setSaving] = useState(false);

  // Fetch flat list for parent selector
  useEffect(() => {
    departmentsApi.list({ view: 'flat' }).then(setAllDepartments).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEditing) {
        const data: UpdateDepartmentRequest = {
          name,
          description: description || undefined,
          parent_id: parentId || undefined,
          sort_order: sortOrder,
          status: status as 'active' | 'archived',
        };
        await departmentsApi.update(department.id, data);
        toast.success(t('departments.updateSuccess'));
      } else {
        const data: CreateDepartmentRequest = {
          name,
          code,
          description: description || undefined,
          parent_id: parentId || undefined,
          sort_order: sortOrder,
        };
        await departmentsApi.create(data);
        toast.success(t('departments.createSuccess'));
      }
      onSaved();
      onClose();
    } catch {
      // Error is handled by apiClient interceptor
    } finally {
      setSaving(false);
    }
  };

  // Build indented options for parent selector
  const buildParentOptions = (depts: Department[], exclude?: string) => {
    const flat: { id: string; name: string; depth: number }[] = [];
    const buildFlat = (list: Department[], depth: number) => {
      for (const d of list) {
        if (d.id !== exclude) {
          flat.push({ id: d.id, name: d.name, depth });
        }
      }
    };
    // Since we fetch flat, just show them. The API returns sorted by sort_order, name
    buildFlat(depts, 0);
    return flat;
  };

  const parentOptions = buildParentOptions(allDepartments, department?.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-6 border-b border-zinc-200 dark:border-zinc-700">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {isEditing ? t('departments.edit') : t('departments.create')}
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('departments.name')} *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={100}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('departments.code')} *
            </label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              disabled={isEditing}
              pattern="^[a-zA-Z0-9_-]+$"
              maxLength={50}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 disabled:opacity-50"
            />
            <p className="mt-1 text-xs text-zinc-500">{t('departments.codeHint')}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('departments.description')}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('departments.parent')}
            </label>
            <select
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            >
              <option value="">--</option>
              {parentOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          {isEditing && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                {t('departments.status')}
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              >
                <option value="active">{t('departments.active')}</option>
                <option value="archived">{t('departments.archived')}</option>
              </select>
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('departments.sortOrder')}
            </label>
            <input
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded-lg transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving || !name || !code}
              className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? t('common.loading') : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─── Department Detail Panel ────────────────────────────────────────────────

interface DepartmentDetailProps {
  department: Department;
  parentName?: string;
  onClose: () => void;
  onEdit: () => void;
}

const DepartmentDetail: React.FC<DepartmentDetailProps> = ({
  department,
  parentName,
  onClose,
  onEdit,
}) => {
  const { t } = useTranslation();

  const statCards = [
    { label: t('departments.members'), value: department.memberCount, icon: Users, color: 'emerald' },
    { label: t('departments.agents'), value: department.agentCount, icon: Bot, color: 'blue' },
    { label: t('departments.knowledge'), value: department.knowledgeCount, icon: Database, color: 'purple' },
  ];

  return (
    <div className="bg-white dark:bg-zinc-800/50 rounded-xl border border-zinc-200 dark:border-zinc-700/50 p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">{department.name}</h3>
          <p className="text-sm text-zinc-500">{department.code}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-500 hover:text-emerald-600"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {department.description && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">{department.description}</p>
      )}

      <div className="grid grid-cols-3 gap-3 mb-4">
        {statCards.map((stat) => (
          <div
            key={stat.label}
            className="p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900/50 text-center"
          >
            <stat.icon className="w-5 h-5 mx-auto mb-1 text-zinc-400" />
            <p className="text-xl font-bold text-zinc-900 dark:text-white">{stat.value}</p>
            <p className="text-xs text-zinc-500">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-2 text-sm">
        {parentName && (
          <div className="flex justify-between">
            <span className="text-zinc-500">{t('departments.parent')}</span>
            <span className="text-zinc-900 dark:text-white">{parentName}</span>
          </div>
        )}
        {department.managerName && (
          <div className="flex justify-between">
            <span className="text-zinc-500">{t('departments.manager')}</span>
            <span className="text-zinc-900 dark:text-white">{department.managerName}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-zinc-500">{t('departments.status')}</span>
          <span
            className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              department.status === 'active'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
            }`}
          >
            {department.status === 'active' ? t('departments.active') : t('departments.archived')}
          </span>
        </div>
        {department.children.length > 0 && (
          <div className="flex justify-between">
            <span className="text-zinc-500">{t('departments.subDepartments')}</span>
            <span className="text-zinc-900 dark:text-white">{department.children.length}</span>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Tree Node Component ────────────────────────────────────────────────────

interface TreeNodeProps {
  dept: Department;
  depth: number;
  isLast: boolean;
  parentLines: boolean[];
  selectedId?: string;
  expandedIds: Set<string>;
  isAdmin: boolean;
  onSelect: (dept: Department) => void;
  onToggle: (id: string) => void;
  onEdit: (dept: Department) => void;
  onDelete: (dept: Department) => void;
}

const DepartmentTreeNode: React.FC<TreeNodeProps> = ({
  dept,
  depth,
  isLast,
  parentLines,
  selectedId,
  expandedIds,
  isAdmin,
  onSelect,
  onToggle,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const hasChildren = dept.children.length > 0;
  const isExpanded = expandedIds.has(dept.id);
  const isSelected = selectedId === dept.id;

  return (
    <>
      <div
        onClick={() => onSelect(dept)}
        className={`group flex items-center gap-0 rounded-lg cursor-pointer transition-all ${
          isSelected
            ? 'bg-emerald-50 dark:bg-emerald-500/10 ring-1 ring-emerald-500/30'
            : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
        }`}
      >
        {/* Tree guide lines + toggle area */}
        <div className="flex items-center flex-shrink-0 self-stretch">
          {/* Ancestor continuation lines */}
          {parentLines.map((showLine, i) => (
            <div
              key={i}
              className="w-6 self-stretch flex justify-center"
            >
              {showLine && (
                <div className="w-px h-full bg-zinc-200 dark:bg-zinc-700" />
              )}
            </div>
          ))}

          {/* Current node connector */}
          {depth > 0 && (
            <div className="w-6 self-stretch flex items-center justify-center relative">
              {/* Vertical line from top to middle */}
              <div
                className={`absolute left-1/2 top-0 w-px -translate-x-1/2 bg-zinc-200 dark:bg-zinc-700 ${
                  isLast ? 'h-1/2' : 'h-full'
                }`}
              />
              {/* Horizontal line from middle to right */}
              <div className="absolute left-1/2 top-1/2 w-1/2 h-px -translate-y-1/2 bg-zinc-200 dark:bg-zinc-700" />
            </div>
          )}

          {/* Expand/collapse toggle */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (hasChildren) onToggle(dept.id);
            }}
            className={`w-7 h-7 flex items-center justify-center rounded-md flex-shrink-0 transition-colors ${
              hasChildren
                ? 'hover:bg-emerald-100 dark:hover:bg-emerald-500/20 text-zinc-500 hover:text-emerald-600'
                : 'text-transparent cursor-default'
            }`}
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )
            ) : (
              <div className="w-1.5 h-1.5 rounded-full bg-zinc-300 dark:bg-zinc-600" />
            )}
          </button>
        </div>

        {/* Department content */}
        <div className="flex-1 flex items-center justify-between py-2.5 pr-3 min-w-0">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={`p-1.5 rounded-lg flex-shrink-0 ${
                hasChildren
                  ? 'bg-emerald-500/10 text-emerald-600'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'
              }`}
            >
              <Building2 className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm text-zinc-900 dark:text-white truncate">
                  {dept.name}
                </span>
                <span className="text-xs text-zinc-400 font-mono flex-shrink-0">{dept.code}</span>
                {dept.status === 'archived' && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-100 text-zinc-500 dark:bg-zinc-700 flex-shrink-0">
                    {t('departments.archived')}
                  </span>
                )}
              </div>
              {dept.description && (
                <p className="text-xs text-zinc-500 mt-0.5 truncate">{dept.description}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
            {/* Stats badges */}
            <div className="hidden sm:flex items-center gap-2.5 text-xs text-zinc-400">
              <span className="flex items-center gap-1" title={t('departments.members')}>
                <Users className="w-3 h-3" /> {dept.memberCount}
              </span>
              <span className="flex items-center gap-1" title={t('departments.agents')}>
                <Bot className="w-3 h-3" /> {dept.agentCount}
              </span>
              <span className="flex items-center gap-1" title={t('departments.knowledge')}>
                <Database className="w-3 h-3" /> {dept.knowledgeCount}
              </span>
            </div>

            {/* Admin actions - only visible on hover */}
            {isAdmin && (
              <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit(dept);
                  }}
                  className="p-1.5 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-600 text-zinc-400 hover:text-emerald-600 transition-colors"
                  title={t('departments.edit')}
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(dept);
                  }}
                  className="p-1.5 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-600 text-zinc-400 hover:text-red-600 transition-colors"
                  title={t('departments.delete')}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Render children */}
      {hasChildren && isExpanded && (
        <div>
          {dept.children.map((child, index) => (
            <DepartmentTreeNode
              key={child.id}
              dept={child}
              depth={depth + 1}
              isLast={index === dept.children.length - 1}
              parentLines={[...parentLines, ...(depth > 0 ? [!isLast] : [])]}
              selectedId={selectedId}
              expandedIds={expandedIds}
              isAdmin={isAdmin}
              onSelect={onSelect}
              onToggle={onToggle}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </>
  );
};

// ─── Flat List Item ─────────────────────────────────────────────────────────

interface FlatItemProps {
  dept: Department;
  selectedId?: string;
  isAdmin: boolean;
  onSelect: (dept: Department) => void;
  onEdit: (dept: Department) => void;
  onDelete: (dept: Department) => void;
}

const DepartmentFlatItem: React.FC<FlatItemProps> = ({
  dept,
  selectedId,
  isAdmin,
  onSelect,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const isSelected = selectedId === dept.id;

  return (
    <div
      onClick={() => onSelect(dept)}
      className={`group flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all ${
        isSelected
          ? 'border-emerald-500/50 bg-emerald-50/50 dark:bg-emerald-500/5'
          : 'border-zinc-200 dark:border-zinc-700/50 bg-white dark:bg-zinc-800/50 hover:border-emerald-300 dark:hover:border-emerald-700'
      }`}
    >
      <div className="flex items-center gap-4">
        <div className="p-2 rounded-lg bg-emerald-500/10">
          <Building2 className="w-5 h-5 text-emerald-600" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-zinc-900 dark:text-white">{dept.name}</h3>
            <span className="text-xs text-zinc-400 font-mono">{dept.code}</span>
            {dept.status === 'archived' && (
              <span className="px-1.5 py-0.5 rounded text-xs bg-zinc-100 text-zinc-500 dark:bg-zinc-700">
                {t('departments.archived')}
              </span>
            )}
          </div>
          {dept.description && (
            <p className="text-sm text-zinc-500 mt-0.5 line-clamp-1">{dept.description}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3 text-xs text-zinc-500">
          <span className="flex items-center gap-1">
            <Users className="w-3.5 h-3.5" /> {dept.memberCount}
          </span>
          <span className="flex items-center gap-1">
            <Bot className="w-3.5 h-3.5" /> {dept.agentCount}
          </span>
          <span className="flex items-center gap-1">
            <Database className="w-3.5 h-3.5" /> {dept.knowledgeCount}
          </span>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit(dept);
              }}
              className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-emerald-600"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(dept);
              }}
              className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-red-600"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        )}
        <ChevronRight className="w-4 h-4 text-zinc-400" />
      </div>
    </div>
  );
};

// ─── Main Departments Page ──────────────────────────────────────────────────

export const Departments: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree');
  const [treeDepts, setTreeDepts] = useState<Department[]>([]);
  const [flatDepts, setFlatDepts] = useState<Department[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showForm, setShowForm] = useState(false);
  const [editingDept, setEditingDept] = useState<Department | undefined>();
  const [selectedDept, setSelectedDept] = useState<Department | null>(null);
  const [loading, setLoading] = useState(true);

  // Build a flat lookup map from tree data for resolving parent names
  const buildFlatMap = useCallback((depts: Department[]): Map<string, Department> => {
    const map = new Map<string, Department>();
    const walk = (list: Department[]) => {
      for (const d of list) {
        map.set(d.id, d);
        if (d.children.length > 0) walk(d.children);
      }
    };
    walk(depts);
    return map;
  }, []);

  const [deptMap, setDeptMap] = useState<Map<string, Department>>(new Map());
  const initialLoadDone = useRef(false);

  const loadDepartments = useCallback(async () => {
    setLoading(true);
    try {
      const [tree, flat] = await Promise.all([
        departmentsApi.list({ view: 'tree' }),
        departmentsApi.list({ view: 'flat' }),
      ]);
      setTreeDepts(tree);
      setFlatDepts(flat);
      setDeptMap(buildFlatMap(tree));

      // Auto-expand root level on first load
      if (!initialLoadDone.current) {
        initialLoadDone.current = true;
        const rootIds = new Set(tree.filter((d) => d.children.length > 0).map((d) => d.id));
        setExpandedIds(rootIds);
      }
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  }, [buildFlatMap]);

  useEffect(() => {
    loadDepartments();
  }, [loadDepartments]);

  const handleRefresh = () => loadDepartments();

  const handleDelete = async (dept: Department) => {
    if (!confirm(t('departments.confirmDelete'))) return;
    try {
      await departmentsApi.delete(dept.id);
      toast.success(t('departments.deleteSuccess'));
      handleRefresh();
      if (selectedDept?.id === dept.id) setSelectedDept(null);
    } catch {
      // Handled by interceptor
    }
  };

  const handleToggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleExpandAll = () => {
    const allIds = new Set<string>();
    const walk = (list: Department[]) => {
      for (const d of list) {
        if (d.children.length > 0) {
          allIds.add(d.id);
          walk(d.children);
        }
      }
    };
    walk(treeDepts);
    setExpandedIds(allIds);
  };

  const handleCollapseAll = () => {
    setExpandedIds(new Set());
  };

  // Count total departments (flat)
  const totalCount = flatDepts.length;

  // Filter for search (use flat list)
  const isSearching = search.trim().length > 0;
  const searchResults = isSearching
    ? flatDepts.filter(
        (d) =>
          d.name.toLowerCase().includes(search.toLowerCase()) ||
          d.code.toLowerCase().includes(search.toLowerCase())
      )
    : [];

  // Get parent name for detail panel
  const parentName = selectedDept?.parentId ? deptMap.get(selectedDept.parentId)?.name : undefined;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-emerald-500/10">
            <Building2 className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
              {t('departments.title')}
            </h1>
            <p className="text-sm text-zinc-500">
              {totalCount} {t('departments.title').toLowerCase()}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={() => {
                setEditingDept(undefined);
                setShowForm(true);
              }}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t('departments.create')}
            </button>
          )}
        </div>
      </div>

      {/* Search + View Toggle */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`${t('common.search')}...`}
            className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        {!isSearching && (
          <div className="flex items-center bg-zinc-100 dark:bg-zinc-800 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('tree')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === 'tree'
                  ? 'bg-white dark:bg-zinc-700 text-emerald-600 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
              title={t('departments.treeView')}
            >
              <FolderTree className="w-3.5 h-3.5" />
              {t('departments.treeView')}
            </button>
            <button
              onClick={() => setViewMode('flat')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === 'flat'
                  ? 'bg-white dark:bg-zinc-700 text-emerald-600 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
              title={t('departments.flatView')}
            >
              <List className="w-3.5 h-3.5" />
              {t('departments.flatView')}
            </button>
          </div>
        )}
        {!isSearching && viewMode === 'tree' && (
          <div className="flex items-center gap-1">
            <button
              onClick={handleExpandAll}
              className="px-2.5 py-1.5 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md transition-colors"
            >
              {t('departments.expandAll')}
            </button>
            <button
              onClick={handleCollapseAll}
              className="px-2.5 py-1.5 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md transition-colors"
            >
              {t('departments.collapseAll')}
            </button>
          </div>
        )}
      </div>

      <div className="flex gap-6">
        {/* Department List / Tree */}
        <div className="flex-1 min-w-0">
          {loading ? (
            <div className="text-center py-12 text-zinc-500">{t('common.loading')}</div>
          ) : isSearching ? (
            // Search results - always flat
            searchResults.length === 0 ? (
              <div className="text-center py-12 text-zinc-500">
                <Search className="w-10 h-10 mx-auto mb-3 text-zinc-300" />
                <p>{t('departments.noSearchResults')}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400 mb-2">
                  {searchResults.length} {t('departments.searchResultCount')}
                </p>
                {searchResults.map((dept) => (
                  <DepartmentFlatItem
                    key={dept.id}
                    dept={dept}
                    selectedId={selectedDept?.id}
                    isAdmin={isAdmin}
                    onSelect={setSelectedDept}
                    onEdit={(d) => {
                      setEditingDept(d);
                      setShowForm(true);
                    }}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )
          ) : viewMode === 'tree' ? (
            // Tree view
            treeDepts.length === 0 ? (
              <div className="text-center py-12 text-zinc-500">
                <Building2 className="w-12 h-12 mx-auto mb-3 text-zinc-300" />
                <p>{t('departments.noData')}</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-zinc-800/30 rounded-xl border border-zinc-200 dark:border-zinc-700/50 p-2">
                {treeDepts.map((dept, index) => (
                  <DepartmentTreeNode
                    key={dept.id}
                    dept={dept}
                    depth={0}
                    isLast={index === treeDepts.length - 1}
                    parentLines={[]}
                    selectedId={selectedDept?.id}
                    expandedIds={expandedIds}
                    isAdmin={isAdmin}
                    onSelect={setSelectedDept}
                    onToggle={handleToggle}
                    onEdit={(d) => {
                      setEditingDept(d);
                      setShowForm(true);
                    }}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )
          ) : (
            // Flat view
            flatDepts.length === 0 ? (
              <div className="text-center py-12 text-zinc-500">
                <Building2 className="w-12 h-12 mx-auto mb-3 text-zinc-300" />
                <p>{t('departments.noData')}</p>
              </div>
            ) : (
              <div className="space-y-2">
                {flatDepts.map((dept) => (
                  <DepartmentFlatItem
                    key={dept.id}
                    dept={dept}
                    selectedId={selectedDept?.id}
                    isAdmin={isAdmin}
                    onSelect={setSelectedDept}
                    onEdit={(d) => {
                      setEditingDept(d);
                      setShowForm(true);
                    }}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )
          )}
        </div>

        {/* Detail Panel */}
        {selectedDept && (
          <div className="w-80 flex-shrink-0">
            <DepartmentDetail
              department={selectedDept}
              parentName={parentName}
              onClose={() => setSelectedDept(null)}
              onEdit={() => {
                setEditingDept(selectedDept);
                setShowForm(true);
              }}
            />
          </div>
        )}
      </div>

      {/* Form Dialog */}
      {showForm && (
        <DepartmentForm
          department={editingDept}
          onClose={() => setShowForm(false)}
          onSaved={handleRefresh}
        />
      )}
    </div>
  );
};

export default Departments;
