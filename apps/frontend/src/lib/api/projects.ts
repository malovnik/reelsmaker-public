/**
 * `/api/v1/projects` — CRUD + Job↔Project binding.
 *
 * Project — logical group of jobs (folder). Scheduler uses `project_id` as
 * source pool of liked reels when building Publer campaigns.
 *
 * Types mirror backend Pydantic DTOs in
 * `videomaker.api.routes.projects` (ProjectRead / ProjectCreate / ProjectUpdate /
 * JobBrief / ProjectDetail / JobProjectAssign).
 */

import { request } from "./core";

export interface Project {
  id: number;
  name: string;
  description: string;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  color?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  color?: string;
}

export interface JobBrief {
  id: string;
  status: string;
  display_name: string | null;
  source_filename: string;
  source_duration_sec: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface ProjectDetail extends Project {
  jobs: JobBrief[];
}

export interface JobProjectAssignResponse {
  job_id: string;
  project_id: number | null;
}

export const projectsApi = {
  listProjects: () => request<Project[]>("/api/v1/projects"),

  createProject: (payload: ProjectCreate) =>
    request<Project>("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getProject: (id: number) =>
    request<ProjectDetail>(`/api/v1/projects/${id}`),

  updateProject: (id: number, payload: ProjectUpdate) =>
    request<Project>(`/api/v1/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deleteProject: (id: number) =>
    request<void>(`/api/v1/projects/${id}`, { method: "DELETE" }),

  assignJobToProject: (jobId: string, projectId: number | null) =>
    request<JobProjectAssignResponse>(`/api/v1/jobs/${jobId}/project`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    }),
};
