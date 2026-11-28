import type { IssueContext } from '../types.ts'

export const PLACEHOLDER_USERNAME = 'YOUR-USERNAME'

const ISSUE_URL = /github\.com\/([\w.-]+)\/([\w.-]+)\/(?:issues|pull)\/(\d+)/i

/** Validate the issue URL and bundle the form values; returns null for a bad URL. */
export function parseIssueForm(rawUrl: string, rawUsername: string, rawIssueText: string): IssueContext | null {
  const url = rawUrl.trim()
  const match = url.match(ISSUE_URL)
  if (!match) return null
  return {
    owner: match[1],
    repo: match[2],
    number: match[3],
    username: rawUsername.trim().replace(/[^\w-]/g, '') || PLACEHOLDER_USERNAME,
    url,
    issueText: rawIssueText.trim(),
  }
}

/** The API expects an empty string, not the placeholder, when no username was given. */
export function usernameForApi(username: string): string {
  return username === PLACEHOLDER_USERNAME ? '' : username
}

/** LLM output is loosely typed: show strings as-is and anything else as readable text. */
export function asText(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(asText).join('\n\n')
  if (value === undefined || value === null) return ''
  return JSON.stringify(value, null, 2)
}

/** One list item: strings as-is, objects as JSON. */
export function itemText(item: unknown): string {
  return typeof item === 'string' ? item : JSON.stringify(item)
}

/** The LLM may return a string or object where a list was asked for; treat that as empty. */
export function asItems(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

/** Only real strings can be file paths. */
export function stringsOnly(value: unknown): string[] {
  return asItems(value).filter((item): item is string => typeof item === 'string')
}
