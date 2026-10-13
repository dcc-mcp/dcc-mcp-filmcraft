export class BridgeError extends Error { readonly code: string; }
export interface CallOptions { signal?: AbortSignal }
export interface ProjectState { name: string; path?: string | null; revision: number; dirty: boolean; root: { id: number; children: unknown[] }; activeSequence: number | null; [key: string]: unknown }
export interface SequenceState { id: number; name: string; durationFrames: number; video: unknown[]; audio: unknown[]; [key: string]: unknown }
export interface ExportJob { id: number; finished: boolean; error?: string; [key: string]: unknown }
export interface NativeSave { path: string; bytes: Uint8Array }
export interface Reconciliation { settled: boolean; uncertain: boolean; ok?: boolean; result?: unknown; error?: string }
export class FilmCraftClient {
  private constructor();
  readonly sessionId: string;
  readonly timeoutMs: number;
  static connect(options: { window?: Window; expectedOrigin: string; sessionId?: string; timeoutMs?: number }): Promise<FilmCraftClient>;
  inspect(): Promise<ProjectState>;
  inspectSequence(sequence: number): Promise<SequenceState>;
  info(): Record<string, unknown>;
  createProject(name: string, options?: CallOptions): Promise<ProjectState>;
  importMedia(file: File, options?: CallOptions): Promise<{items: number[]; errors: unknown[]; paths: string[]}>;
  createSequence(params: {name: string; fromItem: number}, options?: CallOptions): Promise<unknown>;
  renameItem(item: number, name: string, options?: CallOptions): Promise<unknown>;
  setPlaybackRate(params: {sequence: number; clip: number; percent: number}, options?: CallOptions): Promise<unknown>;
  undo(options?: CallOptions): Promise<unknown>;
  redo(options?: CallOptions): Promise<unknown>;
  save(name: string, options?: CallOptions): Promise<NativeSave>;
  reopen(path: string, options?: CallOptions): Promise<ProjectState>;
  exportVideo(params: {name: string; sequence: number; format?: 'h264' | 'wav'}, options?: CallOptions): Promise<{job: number; path: string}>;
  jobs(): Promise<ExportJob[]>;
  cancelExport(job: number): Promise<unknown>;
  readExport(path: string): Promise<Uint8Array>;
  reconcile(): Reconciliation;
  close(): Promise<{closed: true; documentPreserved: true; virtualFilesPreserved: true}>;
}
export function installMessageBridge(options: {
  hostWindow: Window; controllerWindow: Window; allowedOrigin: string; sessionId: string;
  handlers: Record<string, (params: unknown) => unknown | Promise<unknown>>;
}): () => void;
