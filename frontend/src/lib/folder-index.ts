import type { Folder } from '../data/types';
export function createFolderIndex(folders: Folder[]) {
  const index = new Map<string, { folder: Folder; parent?: string; path: string; depth: number }>();
  function visit(items: Folder[], parent?: string, path = '', depth = 1) {
    for (const folder of items) {
      const fullPath = path ? `${path} / ${folder.name}` : folder.name;
      index.set(folder.id, { folder, parent, path: fullPath, depth });
      if (folder.children) visit(folder.children, folder.id, fullPath, depth + 1);
    }
  }
  visit(folders);
  function contains(selected: string, folder?: string): boolean {
    if (!selected) return true;
    for (let id = folder; id; id = index.get(id)?.parent) if (id === selected) return true;
    return false;
  }
  return { index, contains };
}
