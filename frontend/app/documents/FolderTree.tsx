'use client'

// FolderTree — recursive collapsible folder tree for DMS (spec 002 US4, T032).
// Calls GET /cases/{case_id}/folders and renders as an indented tree.
// "New Folder" inline action fires POST /cases/{case_id}/folders.

import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '@/lib/api'

export interface Folder {
  id: string
  case_id: string
  name: string
  parent_folder_id: string | null
  created_by: string | null
  created_at: string
}

interface FolderNodeProps {
  folder: Folder
  children: Folder[]
  allFolders: Folder[]
  selected: string | null
  onSelect: (id: string) => void
  onCreated: (f: Folder) => void
  depth?: number
}

function FolderNode({
  folder, children, allFolders, selected, onSelect, onCreated, depth = 0,
}: FolderNodeProps) {
  const [open, setOpen] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [saving, setSaving] = useState(false)

  const subFolders = children.filter(f => f.parent_folder_id === folder.id)

  async function createSub() {
    if (!newName.trim()) return
    setSaving(true)
    try {
      const created = await apiPost<Folder>(
        `/cases/${folder.case_id}/folders`,
        { name: newName.trim(), parent_folder_id: folder.id }
      )
      onCreated(created)
      setNewName('')
      setAdding(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <li>
      <div
        className={`flex items-center gap-1 rounded px-2 py-1 text-sm cursor-pointer select-none hover:bg-gray-100 ${
          selected === folder.id ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
        }`}
        style={{ paddingRight: `${depth * 16 + 8}px` }}
      >
        <button
          type="button"
          className="shrink-0 w-4 text-gray-400 hover:text-gray-600"
          onClick={() => setOpen(v => !v)}
        >
          {subFolders.length > 0 ? (open ? '▾' : '▸') : ' '}
        </button>
        <span className="flex-1" onClick={() => onSelect(folder.id)}>
          📁 {folder.name}
        </span>
        <button
          type="button"
          title="مجلد فرعي"
          className="shrink-0 text-xs text-gray-400 hover:text-blue-500 opacity-0 group-hover:opacity-100"
          onClick={() => setAdding(v => !v)}
        >
          +
        </button>
      </div>

      {adding && (
        <div className="flex items-center gap-1 pr-8 py-1">
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="اسم المجلد"
            className="flex-1 rounded border border-gray-300 px-2 py-0.5 text-xs"
            onKeyDown={e => { if (e.key === 'Enter') void createSub(); if (e.key === 'Escape') setAdding(false) }}
            autoFocus
          />
          <button
            type="button"
            disabled={saving}
            onClick={() => void createSub()}
            className="text-xs text-blue-600 disabled:opacity-50"
          >
            {saving ? '…' : 'إنشاء'}
          </button>
        </div>
      )}

      {open && subFolders.length > 0 && (
        <ul>
          {subFolders.map(sub => (
            <FolderNode
              key={sub.id}
              folder={sub}
              children={allFolders.filter(f => f.parent_folder_id === sub.id)}
              allFolders={allFolders}
              selected={selected}
              onSelect={onSelect}
              onCreated={onCreated}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

interface FolderTreeProps {
  caseId: string
  selected: string | null
  onSelect: (id: string | null) => void
}

export default function FolderTree({ caseId, selected, onSelect }: FolderTreeProps) {
  const [folders, setFolders] = useState<Folder[]>([])
  const [loading, setLoading] = useState(true)
  const [newRootName, setNewRootName] = useState('')
  const [addingRoot, setAddingRoot] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    apiGet<Folder[]>(`/cases/${caseId}/folders`)
      .then(setFolders)
      .catch(() => setFolders([]))
      .finally(() => setLoading(false))
  }, [caseId])

  const roots = folders.filter(f => f.parent_folder_id === null)

  function handleCreated(f: Folder) {
    setFolders(prev => [...prev, f])
  }

  async function createRoot() {
    if (!newRootName.trim()) return
    setSaving(true)
    try {
      const created = await apiPost<Folder>(`/cases/${caseId}/folders`, { name: newRootName.trim() })
      setFolders(prev => [...prev, created])
      setNewRootName('')
      setAddingRoot(false)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-xs text-gray-400 px-2 py-1">جارٍ التحميل…</div>
  }

  return (
    <div className="text-sm">
      <div className="flex items-center justify-between px-2 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wide">
        <span>المجلدات</span>
        <button
          type="button"
          onClick={() => { onSelect(null); setAddingRoot(v => !v) }}
          className="text-blue-500 hover:text-blue-700"
          title="مجلد جديد في الجذر"
        >
          + مجلد
        </button>
      </div>

      {addingRoot && (
        <div className="flex items-center gap-1 px-2 py-1">
          <input
            type="text"
            value={newRootName}
            onChange={e => setNewRootName(e.target.value)}
            placeholder="اسم المجلد"
            className="flex-1 rounded border border-gray-300 px-2 py-0.5 text-xs"
            onKeyDown={e => { if (e.key === 'Enter') void createRoot(); if (e.key === 'Escape') setAddingRoot(false) }}
            autoFocus
          />
          <button type="button" disabled={saving} onClick={() => void createRoot()} className="text-xs text-blue-600 disabled:opacity-50">
            {saving ? '…' : 'إنشاء'}
          </button>
        </div>
      )}

      {roots.length === 0 && !addingRoot && (
        <p className="px-2 py-1 text-xs text-gray-400">لا توجد مجلدات — أنشئ مجلدًا للبدء</p>
      )}

      <ul className="group">
        {roots.map(folder => (
          <FolderNode
            key={folder.id}
            folder={folder}
            children={folders.filter(f => f.parent_folder_id === folder.id)}
            allFolders={folders}
            selected={selected}
            onSelect={onSelect}
            onCreated={handleCreated}
          />
        ))}
      </ul>
    </div>
  )
}
