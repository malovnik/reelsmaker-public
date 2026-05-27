import { createBrowserRouter } from "react-router-dom";
import { lazy, Suspense } from "react";

import RootLayout from "@/pages/RootLayout";
import SettingsLayout from "@/pages/SettingsLayout";
import NotFoundPage from "@/pages/NotFoundPage";

import HomePage, { loader as homeLoader } from "@/pages/HomePage";
import JobDetailPage, { loader as jobLoader } from "@/pages/JobDetailPage";
import ClipDetailPage, { loader as clipLoader } from "@/pages/ClipDetailPage";
import JobTinderPage, { loader as tinderLoader } from "@/pages/JobTinderPage";
import ProjectsPage, { loader as projectsLoader } from "@/pages/ProjectsPage";
// FE-2 создаёт pages/ProjectFolderPage.tsx параллельно — lazy-импорт по
// ожидаемому пути (экран папки saved/<folder> проекта, R2.2).
const ProjectFolderPage = lazy(() => import("@/pages/ProjectFolderPage"));
import MaintenancePage from "@/pages/MaintenancePage";
import SchedulerPage, {
  loader as schedulerLoader,
} from "@/pages/SchedulerPage";
import AccountsPage, { loader as accountsLoader } from "@/pages/AccountsPage";
import NewCampaignPage, {
  loader as newCampaignLoader,
} from "@/pages/NewCampaignPage";
import PresetsPage, { loader as presetsLoader } from "@/pages/PresetsPage";
import CampaignDetailPage, {
  loader as campaignDetailLoader,
} from "@/pages/CampaignDetailPage";
import BrandKitPage from "@/pages/BrandKitPage";
import ModelsPage, { loader as modelsLoader } from "@/pages/ModelsPage";
import PerformanceSettingsPage, {
  loader as performanceLoader,
} from "@/pages/PerformanceSettingsPage";
import PostProductionSettingsPage, {
  loader as postProdLoader,
} from "@/pages/PostProductionSettingsPage";
import VisionProfilesPage, {
  loader as visionLoader,
} from "@/pages/VisionProfilesPage";
import PromptsPage, { loader as promptsLoader } from "@/pages/PromptsPage";
import SubtitleSettingsPage, {
  loader as subtitlesLoader,
} from "@/pages/SubtitleSettingsPage";

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <NotFoundPage />,
    children: [
      { index: true, element: <HomePage />, loader: homeLoader },

      { path: "projects", element: <ProjectsPage />, loader: projectsLoader },
      {
        path: "projects/:id/folder",
        element: (
          <Suspense fallback={<div className="p-8 text-sm">Загрузка…</div>}>
            <ProjectFolderPage />
          </Suspense>
        ),
      },

      {
        path: "jobs/:id",
        element: <JobDetailPage />,
        loader: jobLoader,
      },
      {
        path: "jobs/:id/reels/:reelId",
        element: <ClipDetailPage />,
        loader: clipLoader,
      },
      {
        path: "jobs/:id/tinder",
        element: <JobTinderPage />,
        loader: tinderLoader,
      },

      {
        path: "scheduler",
        element: <SchedulerPage />,
        loader: schedulerLoader,
      },
      {
        path: "scheduler/accounts",
        element: <AccountsPage />,
        loader: accountsLoader,
      },
      {
        path: "scheduler/new",
        element: <NewCampaignPage />,
        loader: newCampaignLoader,
      },
      {
        path: "scheduler/presets",
        element: <PresetsPage />,
        loader: presetsLoader,
      },
      {
        path: "scheduler/campaigns/:id",
        element: <CampaignDetailPage />,
        loader: campaignDetailLoader,
      },

      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { path: "brand", element: <BrandKitPage /> },
          { path: "maintenance", element: <MaintenancePage /> },
          {
            path: "models",
            element: <ModelsPage />,
            loader: modelsLoader,
          },
          {
            path: "performance",
            element: <PerformanceSettingsPage />,
            loader: performanceLoader,
          },
          {
            path: "post-production",
            element: <PostProductionSettingsPage />,
            loader: postProdLoader,
          },
          {
            path: "profiles",
            element: <VisionProfilesPage />,
            loader: visionLoader,
          },
          {
            path: "prompts",
            element: <PromptsPage />,
            loader: promptsLoader,
          },
          {
            path: "subtitles",
            element: <SubtitleSettingsPage />,
            loader: subtitlesLoader,
          },
        ],
      },

      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
