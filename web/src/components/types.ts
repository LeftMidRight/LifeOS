import type { Entry, Kind } from '../../../shared/schema.ts';

export interface ToastAction {
  label: string;
  run: () => void | Promise<void>;
}

export type Notify = (message: string, action?: ToastAction) => void;

export interface ViewProps {
  entries: Entry[];
  refresh: () => Promise<void>;
  notify: Notify;
}

/** 记录类型的中文短标签，用于按钮组 */
export const PRIMARY_KINDS: Kind[] = ['journal', 'thought', 'expense', 'todo'];
