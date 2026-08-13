/**
 * Handing a document to the operator as a file, without inventing anything.
 *
 * What is written to disk is the server's own JSON, serialised and nothing else:
 * no field renamed, no key dropped, no ordering imposed. A file the operator
 * archives or sends to an auditor has to be the artefact the engine emitted, not
 * this client's rendering of it.
 */

export function downloadJson(name: string, document: unknown): void {
  const blob = new Blob([JSON.stringify(document, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')

  link.href = url
  link.download = name
  window.document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoking immediately can race the download in some browsers; one tick is
  // enough and the object is not kept alive any longer than that.
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** `soa-3f2b1a09.json`: short, sortable by nothing, and unambiguous about which baseline. */
export const fileName = (kind: string, baselineId: string): string =>
  `${kind}-${baselineId.slice(0, 8)}.json`
