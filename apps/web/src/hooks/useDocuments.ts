import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteDocument, listDocuments, uploadDocument } from '../api.ts'
import { useChatStore } from '../store.ts'
import { validateFile } from '../upload.ts'

const DOCUMENTS_KEY = ['documents']

export interface UploadFailure {
  filename: string
  message: string
}

export interface UploadProgress {
  done: number
  total: number
  current: string
}

interface UploadVariables {
  files: File[]
  onProgress: (progress: UploadProgress) => void
}

export function useDocuments() {
  return useQuery({ queryKey: DOCUMENTS_KEY, queryFn: listDocuments })
}

async function uploadFiles({ files, onProgress }: UploadVariables): Promise<UploadFailure[]> {
  const failures: UploadFailure[] = []
  for (const [done, file] of files.entries()) {
    onProgress({ done, total: files.length, current: file.name })
    const problem = validateFile(file)
    if (problem) {
      failures.push({ filename: file.name, message: problem })
      continue
    }
    try {
      await uploadDocument(file)
    } catch (error) {
      failures.push({ filename: file.name, message: (error as Error).message })
    }
  }
  return failures
}

export function useUploadDocuments() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: uploadFiles,
    onSettled: () => queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY }),
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: (_data, id) => {
      const { selectedDocumentIds, toggleDocument } = useChatStore.getState()
      if (selectedDocumentIds.includes(id)) toggleDocument(id)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY }),
  })
}
