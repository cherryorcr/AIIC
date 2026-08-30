import { Fragment, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  healthCheck,
  createTemporaryUser,
  getCurrentUser,
  getSessionSummary,
  getWorkspaceOverview,
  listFavorites,
  listJobs,
  listKnowledgeItems,
  listReports,
  listSessionHistory,
  loadFavorites,
  loadUserProfile,
  loginAccount,
  logoutAccount,
  completeSession,
  confirmDocument,
  deleteDocument,
  listDocuments,
  previewMatch,
  queueQuestion,
  runAlgorithm,
  registerAccount,
  saveUserProfile,
  startSession,
  subscribeWorkspaceUpdates,
  submitTurn,
  toggleFavorite,
  uploadDocument,
} from "./api";
import type { AlgorithmResult, AuthState, BackendQuestion, CandidateDocument, DocumentKind, Feedback as BackendFeedback, MatchResponse, SessionSummary, StartSessionResponse, UserProfile, WorkspaceOverview } from "./api";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  Bell,
  BookOpen,
  BrainCircuit,
  BriefcaseBusiness,
  ArrowLeftRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Code2,
  Database,
  FileCheck2,
  FileQuestion,
  FileText,
  FolderOpen,
  Gauge,
  GitBranch,
  LayoutDashboard,
  LibraryBig,
  LockKeyhole,
  LogIn,
  LogOut,
  Mail,
  Menu,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  RotateCcw,
  Route as RouteIcon,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TimerReset,
  Trash2,
  UploadCloud,
  Users,
  UserRound,
  X,
} from "lucide-react";

type ModeId = "technical" | "algorithm" | "behavioral" | "stress" | "case" | "research" | "hr" | "group";

type ModeMeta = {
  id: ModeId;
  label: string;
  shortLabel: string;
  description: string;
  helper: string;
  Icon: LucideIcon;
  color: string;
};

type Question = {
  id: string;
  mode: ModeId;
  title: string;
  prompt: string;
  skills: string[];
  difficulty: string;
  source: string;
  sourceUrl?: string;
  sourceLicense?: string;
  sourceConfidence?: string;
  sourceVersion?: string;
  personalized?: boolean;
  sourceQuestionId?: string;
  personalizationBasis?: string[];
  followUp: string;
  rubric: string[];
  tests?: Array<{
    args?: unknown[];
    kwargs?: Record<string, unknown>;
    expected?: unknown;
  }>;
  backend?: BackendQuestion;
};

type ConversationMessage = {
  id: string;
  kind: "assistant" | "user" | "peer";
  speaker: string;
  role?: string;
  content: string;
};

const modeMeta: ModeMeta[] = [
  {
    id: "technical",
    label: "技术面",
    shortLabel: "技术",
    description: "考察正确性、复杂度与技术取舍",
    helper: "适合检验项目深度和系统设计表达",
    Icon: BrainCircuit,
    color: "blue",
  },
  {
    id: "algorithm",
    label: "算法面",
    shortLabel: "算法",
    description: "在线运行 Python，校验思路和复杂度",
    helper: "固定测试用例 + 受限沙箱执行",
    Icon: Code2,
    color: "purple",
  },
  {
    id: "behavioral",
    label: "行为面",
    shortLabel: "行为",
    description: "用 STAR 结构讲清贡献、结果与复盘",
    helper: "系统会根据经历连续追问",
    Icon: MessageSquareText,
    color: "mint",
  },
  {
    id: "stress",
    label: "压力面",
    shortLabel: "压力",
    description: "限时回答，训练稳定表达和抗压",
    helper: "默认 30 秒，追问强度逐步增加",
    Icon: TimerReset,
    color: "coral",
  },
  {
    id: "case",
    label: "案例面",
    shortLabel: "案例",
    description: "拆解问题、设计指标并验证假设",
    helper: "从结构化思考走到可执行方案",
    Icon: RouteIcon,
    color: "amber",
  },
  {
    id: "research",
    label: "科研面",
    shortLabel: "科研",
    description: "聚焦研究假设、实验设计和局限",
    helper: "适合研究生、算法和科研岗位",
    Icon: LibraryBig,
    color: "indigo",
  },
  {
    id: "hr",
    label: "HR 面",
    shortLabel: "HR",
    description: "动机、匹配度和入职预期",
    helper: "让回答具体、真实、不过度包装",
    Icon: BriefcaseBusiness,
    color: "slate",
  },
  {
    id: "group",
    label: "群面",
    shortLabel: "群面",
    description: "围绕一个开放问题协作、质疑并达成共识",
    helper: "AI 模拟主持人和队友，按阶段推进讨论",
    Icon: Users,
    color: "indigo",
  },
];

const questions: Question[] = [
  {
    id: "Q001",
    mode: "technical",
    title: "数据结构与复杂度取舍",
    prompt: "请解释你在一个项目中如何选择数据结构，并说明时间复杂度取舍。",
    skills: ["数据结构", "复杂度分析"],
    difficulty: "中",
    source: "synthetic_mock · TechMatch 题库",
    followUp: "如果数据规模扩大十倍，你会怎么改？",
    rubric: ["结合真实项目", "说清复杂度", "解释技术取舍"],
  },
  {
    id: "Q002",
    mode: "technical",
    title: "线上接口延迟升高",
    prompt: "线上接口延迟突然升高，你会如何定位问题？请说出排查顺序和止损方案。",
    skills: ["系统设计", "故障排查"],
    difficulty: "中高",
    source: "synthetic_mock · TechMatch 题库",
    followUp: "监控没有明显异常时，你的下一步是什么？",
    rubric: ["先确认现象", "提出可验证假设", "有回滚或止损方案"],
  },
  {
    id: "Q003",
    mode: "algorithm",
    title: "最长无重复子串",
    prompt: "给定一个字符串，请返回不含重复字符的最长子串长度。要求说明时间复杂度。",
    skills: ["滑动窗口", "哈希表"],
    difficulty: "中",
    source: "synthetic_mock · 算法题样例",
    followUp: "如果字符集非常大，如何降低额外空间？",
    rubric: ["边界完整", "复杂度正确", "代码可运行"],
  },
  {
    id: "Q004",
    mode: "behavioral",
    title: "主动发现并解决问题",
    prompt: "讲一个你主动发现并解决问题的项目经历。请按背景、行动、结果和复盘组织。",
    skills: ["项目 ownership", "沟通协作"],
    difficulty: "中",
    source: "synthetic_mock · 行为面样例",
    followUp: "如果不解决会造成什么影响？你如何证明结果有效？",
    rubric: ["背景清楚", "行动由本人完成", "结果有证据", "有复盘"],
  },
  {
    id: "Q005",
    mode: "stress",
    title: "没有证据，为什么相信你？",
    prompt: "你刚才的回答没有证据，为什么我们要相信你？请在 30 秒内重新回答。",
    skills: ["抗压", "自我认知"],
    difficulty: "中高",
    source: "synthetic_mock · 压力面样例",
    followUp: "请把刚才的回答压缩成一句结论和一个事实。",
    rubric: ["保持冷静", "不防御性争辩", "补充具体事实", "控制时间"],
  },
  {
    id: "Q006",
    mode: "case",
    title: "活跃率下降的原因拆解",
    prompt: "某功能上线后活跃率下降，你会如何拆解并验证原因？先定义指标，再提出验证方案。",
    skills: ["指标设计", "因果分析"],
    difficulty: "中高",
    source: "synthetic_mock · 案例面样例",
    followUp: "哪些分群和对照实验最先看？",
    rubric: ["定义指标", "拆分维度", "区分相关与因果", "提出验证方案"],
  },
  {
    id: "Q007",
    mode: "research",
    title: "最关键的研究假设",
    prompt: "你项目中最关键的假设是什么？如果它不成立，结论会怎样？",
    skills: ["研究设计", "批判性思维"],
    difficulty: "中高",
    source: "synthetic_mock · 科研面样例",
    followUp: "你如何设计一个最小验证实验？",
    rubric: ["明确假设", "承认限制", "有替代解释", "验证可执行"],
  },
  {
    id: "Q008",
    mode: "hr",
    title: "为什么选择这个岗位",
    prompt: "为什么选择这个岗位？你希望在入职后解决什么问题？",
    skills: ["动机", "岗位匹配"],
    difficulty: "低中",
    source: "synthetic_mock · HR 面样例",
    followUp: "为什么不是其他相近岗位？",
    rubric: ["动机具体", "与岗位要求相关", "避免空泛口号"],
  },
];

const navItems: Array<{
  label: string;
  path: string;
  Icon: LucideIcon;
  end?: boolean;
}> = [
  { label: "总览", path: "/", Icon: LayoutDashboard, end: true },
  { label: "开始训练", path: "/practice", Icon: Sparkles },
  { label: "岗位匹配", path: "/match", Icon: Target },
  { label: "求职资料", path: "/materials", Icon: FolderOpen },
  { label: "题库", path: "/questions", Icon: FileQuestion },
  { label: "训练报告", path: "/reports", Icon: BarChart3 },
];

type DashboardSession = {
  title: string;
  mode: string;
  score: number | null;
  date: string;
  accent: string;
};

function App() {
  return (
    <BrowserRouter>
      <AuthBootstrap />
    </BrowserRouter>
  );
}

function AuthBootstrap() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getCurrentUser()
      .then(setAuth)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "用户服务暂不可用"));
  }, []);
  if (!auth) {
    return (
      <div className="auth-loading">
        <BrainCircuit size={30} />
        <strong>{error || "正在加载你的独立工作区..."}</strong>
        {error ? (
          <button className="secondary-button" type="button" onClick={() => globalThis.location.reload()}>
            重试
          </button>
        ) : null}
      </div>
    );
  }
  return <AppShell key={auth.user.id} auth={auth} onAuthChange={setAuth} />;
}

function AppShell({ auth, onAuthChange }: { auth: AuthState; onAuthChange: (value: AuthState) => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const title = getPageTitle(location.pathname);
  const displayName = auth.user.display_name || (auth.authenticated ? auth.user.email : "临时用户");
  const avatar = String(displayName || "U")
    .trim()
    .slice(0, 1)
    .toUpperCase();

  return (
    <div className={collapsed ? "app-shell app-shell-collapsed" : "app-shell"}>
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} onToggle={() => setCollapsed((value) => !value)} />
      <div className="app-main">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="打开导航" onClick={() => setMobileOpen(true)}>
            <Menu size={19} />
          </button>
          <div className="topbar-heading">
            <span className="breadcrumb">TechMatch / 工作区</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <div className="system-status">
              <span className="status-dot" />
              模型服务正常
            </div>
            <button className="icon-button" type="button" aria-label="通知">
              <Bell size={18} />
            </button>
            <button className="profile-menu" type="button" onClick={() => navigate("/account")}>
              <span className="avatar">{avatar}</span>
              <span className="profile-name">{displayName}</span>
              <ChevronDown size={15} />
            </button>
          </div>
        </header>
        <main className="page-container">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/practice" element={<PracticePage />} />
            <Route path="/match" element={<MatchPage />} />
            <Route path="/materials" element={<MaterialsPage />} />
            <Route path="/questions" element={<QuestionBankPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/account" element={<AccountPage auth={auth} onAuthChange={onAuthChange} />} />
            <Route path="*" element={<DashboardPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Sidebar({ collapsed, mobileOpen, onClose, onToggle }: { collapsed: boolean; mobileOpen: boolean; onClose: () => void; onToggle: () => void }) {
  const navigate = useNavigate();
  return (
    <>
      {mobileOpen ? <button className="sidebar-backdrop" aria-label="关闭导航" type="button" onClick={onClose} /> : null}
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "sidebar-mobile-open" : ""}`}>
        <div className="brand-row">
          <NavLink className="brand" to="/" onClick={onClose}>
            <span className="brand-mark">
              <img src="/techmatch-logo.svg" alt="TechMatch" />
            </span>
            <span className="brand-text">
              <strong>TechMatch</strong>
              <small>AI 面试陪练</small>
            </span>
          </NavLink>
          <button className="icon-button sidebar-close" type="button" aria-label="关闭导航" onClick={onClose}>
            <X size={17} />
          </button>
          <button className="icon-button sidebar-collapse" type="button" aria-label={collapsed ? "展开侧栏" : "收起侧栏"} onClick={onToggle}>
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>
        <button
          className="new-session-button"
          type="button"
          onClick={() => {
            navigate("/practice");
            onClose();
          }}
        >
          <Plus size={18} />
          <span>新建训练</span>
        </button>
        <nav className="side-nav" aria-label="主导航">
          <span className="nav-label">工作台</span>
          {navItems.map(({ label, path, Icon, end }) => (
            <NavLink key={path} className={({ isActive }) => (isActive ? "side-link active" : "side-link")} end={end} to={path} onClick={onClose}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
          <span className="nav-label nav-label-spaced">管理</span>
          <NavLink className={({ isActive }) => (isActive ? "side-link active" : "side-link")} to="/settings" onClick={onClose}>
            <Settings2 size={18} />
            <span>系统设置</span>
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-model-card">
            <div className="model-icon">
              <CpuIcon />
            </div>
            <div>
              <strong>本地模型</strong>
              <span>双卡 4090 · 在线</span>
            </div>
            <span className="online-dot" />
          </div>
          <div className="sidebar-footnote">
            <ShieldCheck size={14} /> 数据仅用于本次训练
          </div>
        </div>
      </aside>
    </>
  );
}

function CpuIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="5" y="5" width="14" height="14" rx="2" />
      <path d="M9 9h6v6H9zM9 1v4M15 1v4M9 19v4M15 19v4M19 9h4M19 14h4M1 9h4M1 14h4" />
    </svg>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [overviewError, setOverviewError] = useState("");
  useEffect(() => {
    let active = true;
    const loadOverview = () => {
      void getWorkspaceOverview()
        .then((result) => {
          if (!active) return;
          setOverview(result);
          setOverviewError("");
        })
        .catch((cause) => {
          if (active) setOverviewError(cause instanceof Error ? cause.message : "准备度加载失败");
        });
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") loadOverview();
    };
    loadOverview();
    const unsubscribe = subscribeWorkspaceUpdates(loadOverview);
    globalThis.addEventListener("focus", loadOverview);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      active = false;
      unsubscribe();
      globalThis.removeEventListener("focus", loadOverview);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);
  const readiness = overview?.readiness;
  const score = readiness?.score ?? 0;
  const hasTargetJob = Boolean(overview?.latest_job);
  const dashboardSessions: DashboardSession[] = (overview?.recent_sessions || []).map((item) => {
    const rawScore = Number(item.summary?.average_score ?? item.average_score);
    return {
      title: `${item.role || "未命名岗位"} · ${getModeLabel(item.mode || "technical")}`,
      mode: getModeLabel(item.mode || "technical"),
      score: Number.isFinite(rawScore) ? Math.round(rawScore * 20) : null,
      date: formatDate(item.updated_at || item.created_at),
      accent: item.mode === "algorithm" ? "purple" : item.mode === "case" ? "amber" : "blue",
    };
  });
  const latestSession = dashboardSessions[0];
  const personalizedSuggestions = readiness?.skill_gaps.length
    ? readiness.skill_gaps.slice(0, 3).map((skill, index) => ({
        title: skill,
        detail: `目标 JD 需要该能力，建议加入下一轮${index === 0 ? "技术" : "专项"}训练。`,
        progress: readiness.skill_coverage,
        color: ["blue", "mint", "coral"][index],
      }))
    : [
        {
          title: "完善目标 JD",
          detail: "保存岗位描述后生成技能缺口。",
          progress: readiness?.profile_completeness ?? 0,
          color: "blue",
        },
        {
          title: "补充项目证据",
          detail: "写清个人贡献、数据结果和复盘。",
          progress: readiness?.training_score ?? 0,
          color: "mint",
        },
        {
          title: "开始场景训练",
          detail: "完成回答后更新个性化准备度。",
          progress: Math.min(100, (overview?.counts.sessions ?? 0) * 20),
          color: "coral",
        },
      ];
  return (
    <div className="dashboard-page">
      <section className="welcome-row">
        <div>
          <span className="eyebrow">星期一，08 月 30 日</span>
          <h2>准备好，开始下一轮练习。</h2>
          <p>把目标岗位拆成可训练的技能，用一次短练习换来更确定的表达。</p>
        </div>
        <button className="primary-button" type="button" onClick={() => navigate("/practice")}>
          <Sparkles size={17} />
          开始训练 <ArrowRight size={16} />
        </button>
      </section>
      <section className="overview-grid">
        <article className="readiness-card">
          <div className="card-header">
            <div>
              <span className="eyebrow">岗位准备度</span>
              <h3>{readiness?.role || "正在计算你的岗位准备度"}</h3>
            </div>
            <button className="text-button" type="button" onClick={() => navigate("/match")}>
              查看匹配 <ArrowRight size={15} />
            </button>
          </div>
          <div className="readiness-body">
            <div
              className="score-ring"
              style={{
                background: `conic-gradient(var(--blue) 0 ${hasTargetJob ? score : 0}%, #e8edf5 ${hasTargetJob ? score : 0}% 100%)`,
              }}
            >
              <span>{hasTargetJob ? score : "—"}</span>
              <small>/100</small>
            </div>
            <div className="readiness-copy">
              <strong>{readiness?.label || (overviewError ? "准备度暂不可用" : "正在读取个人工作区")}</strong>
              <p>{readiness?.skill_gaps.length ? `优先补齐：${readiness.skill_gaps.slice(0, 3).join("、")}` : "完善个人背景和目标 JD 后，系统会生成个性化能力缺口。"}</p>
              <div className="progress-line">
                <span style={{ width: `${hasTargetJob ? score : 0}%` }} />
              </div>
              <div className="progress-meta">
                <span>档案完整度 {readiness?.profile_completeness ?? 0}%</span>
                <span>{hasTargetJob ? "目标 85" : "保存 JD 后开始评分"}</span>
              </div>
            </div>
          </div>
          <div className="skill-strip">
            <span>
              <i className="mini-dot mint" />
              已掌握 <b>{readiness?.matched_skills.length ?? 0}</b>
            </span>
            <span>
              <i className="mini-dot coral" />
              待加强 <b>{readiness?.skill_gaps.length ?? 0}</b>
            </span>
            <span>
              <i className="mini-dot blue" />
              已完成训练 <b>{overview?.counts.sessions ?? 0}</b>
            </span>
          </div>
        </article>
        <article className="next-session-card">
          <div className="card-header">
            <div>
              <span className="eyebrow">继续上次训练</span>
              <h3>{latestSession?.title || "还没有进行中的训练"}</h3>
            </div>
            <span className="small-tag blue-tag">{latestSession?.mode || "待开始"}</span>
          </div>
          <div className="session-detail">
            <div className="session-icon">
              <Database size={22} />
            </div>
            <div>
              <strong>{latestSession ? `最近得分 ${latestSession.score ?? "—"}` : "从目标岗位开始"}</strong>
              <span>{latestSession?.date || "完成一次训练后可从这里继续复盘"}</span>
            </div>
          </div>
          <button className="secondary-button full-button" type="button" onClick={() => navigate("/practice")}>
            继续训练 <ArrowRight size={16} />
          </button>
        </article>
      </section>
      <section className="content-grid dashboard-content-grid">
        <div className="main-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">训练入口</span>
              <h3>按场景选择今天的练习</h3>
            </div>
            <button className="text-button" type="button" onClick={() => navigate("/practice")}>
              全部场景 <ArrowRight size={15} />
            </button>
          </div>
          <div className="mode-grid">
            {modeMeta.slice(0, 6).map((mode) => (
              <ModeCard key={mode.id} mode={mode} onClick={() => navigate("/practice")} />
            ))}
          </div>
          <div className="section-heading recent-heading">
            <div>
              <span className="eyebrow">最近训练</span>
              <h3>保持节奏，持续迭代</h3>
            </div>
            <button className="text-button" type="button" onClick={() => navigate("/reports")}>
              查看报告 <ArrowRight size={15} />
            </button>
          </div>
          <div className="session-list">
            {dashboardSessions.map((session) => (
              <SessionRow key={session.title} session={session} />
            ))}
            {!dashboardSessions.length ? (
              <div className="empty-list">
                <Clock3 size={20} />
                <p>当前账户暂无训练记录。</p>
              </div>
            ) : null}
          </div>
        </div>
        <aside className="right-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">今日建议</span>
              <h3>先补齐这三项</h3>
            </div>
            <CircleHelp size={17} className="muted-icon" />
          </div>
          <div className="recommendation-list">
            {personalizedSuggestions.map((item) => (
              <RecommendationItem key={item.title} icon={<GitBranch size={18} />} {...item} />
            ))}
          </div>
          <div className="source-note">
            <ShieldCheck size={16} />
            <div>
              <strong>可解释推荐</strong>
              <p>每道题都关联岗位技能、面试场景和数据来源。</p>
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}

function ModeCard({ mode, onClick }: { mode: ModeMeta; onClick: () => void }) {
  const { Icon } = mode;
  return (
    <button className={`mode-card mode-${mode.color}`} type="button" onClick={onClick}>
      <span className="mode-icon">
        <Icon size={19} />
      </span>
      <span className="mode-card-copy">
        <strong>{mode.label}</strong>
        <small>{mode.description}</small>
      </span>
      <ArrowRight size={16} className="mode-arrow" />
    </button>
  );
}

function RecommendationItem({ icon, title, detail, progress, color }: { icon: ReactNode; title: string; detail: string; progress: number; color: string }) {
  return (
    <div className="recommendation-item">
      <div className={`recommendation-icon icon-${color}`}>{icon}</div>
      <div className="recommendation-copy">
        <div>
          <strong>{title}</strong>
          <span>{progress}%</span>
        </div>
        <p>{detail}</p>
        <div className="tiny-progress">
          <span className={`fill-${color}`} style={{ width: `${progress}%` }} />
        </div>
      </div>
    </div>
  );
}

function SessionRow({ session }: { session: DashboardSession }) {
  return (
    <div className="session-row">
      <span className={`session-accent accent-${session.accent}`} />
      <div className="session-row-icon">
        <Clock3 size={17} />
      </div>
      <div className="session-row-copy">
        <strong>{session.title}</strong>
        <span>
          {session.mode} · {session.date}
        </span>
      </div>
      <div className="session-score">
        <strong>{session.score ?? "—"}</strong>
        <span>{session.score === null ? "" : "分"}</span>
      </div>
      <ArrowRight size={16} className="muted-icon" />
    </div>
  );
}

function questionTitleFromPrompt(prompt: string): string {
  const cleaned = prompt
    .replace(/\s+/g, " ")
    .replace(/[（(][^）)]{0,100}(?:依据|source|转载|转写|leetcode)[^）)]*[）)]/gi, "")
    .trim();
  const firstClause = cleaned.split(/[。！？!?：:]/, 1)[0]?.trim() || cleaned;
  if (!firstClause) return "待训练面试题";
  return firstClause.length > 28 ? `${firstClause.slice(0, 28)}…` : firstClause;
}

function backendQuestionToQuestion(item: BackendQuestion, mode: ModeId, fallback?: Question): Question {
  const prompt = item.question || fallback?.prompt || "请介绍一个与目标岗位相关的项目。";
  const sameQuestion = Boolean(fallback && fallback.id === item.question_id);
  return {
    id: item.question_id,
    mode,
    title: item.title?.trim() || (sameQuestion ? fallback?.title : undefined) || questionTitleFromPrompt(prompt),
    prompt,
    skills: item.skills?.length ? item.skills : sameQuestion ? fallback?.skills || [] : [],
    difficulty: item.difficulty || (sameQuestion ? fallback?.difficulty : undefined) || "中",
    source: item.source_refs?.length ? item.source_refs.join(" · ") : sameQuestion ? fallback?.source || "synthetic_mock" : "synthetic_mock",
    sourceUrl: typeof item.source?.url === "string" ? item.source.url : sameQuestion ? fallback?.sourceUrl : undefined,
    sourceLicense: typeof item.source?.license === "string" ? item.source.license : sameQuestion ? fallback?.sourceLicense : undefined,
    sourceConfidence: item.source_confidence || (sameQuestion ? fallback?.sourceConfidence : undefined),
    sourceVersion: typeof item.source?.version === "string" ? item.source.version : sameQuestion ? fallback?.sourceVersion : undefined,
    personalized: Boolean(item.personalized),
    sourceQuestionId: item.source_question_id,
    personalizationBasis: item.personalization_basis || [],
    followUp: item.follow_ups?.join(" ") || (sameQuestion ? fallback?.followUp : undefined) || "请补充一个具体事实或结果。",
    rubric: item.rubric?.length ? item.rubric : sameQuestion ? fallback?.rubric || [] : [],
    tests: item.tests || (sameQuestion ? fallback?.tests : undefined),
    backend: item,
  };
}

function modeFromProcessType(value?: string): ModeId {
  const map: Record<string, ModeId> = {
    技术面: "technical",
    算法面: "algorithm",
    行为面: "behavioral",
    压力面: "stress",
    案例面: "case",
    科研面: "research",
    HR面: "hr",
    "HR 面": "hr",
    群面: "group",
  };
  return map[value || ""] || (modeMeta.some((item) => item.id === value) ? (value as ModeId) : "technical");
}

function questionFromKnowledge(item: BackendQuestion): Question {
  const mode = modeFromProcessType(item.process_type);
  const fallback = questions.find((candidate) => candidate.id === (item.id || item.question_id) && candidate.mode === mode) || questions.find((candidate) => candidate.mode === mode);
  return backendQuestionToQuestion(
    {
      ...item,
      question_id: item.question_id || item.id || `Q-${Date.now()}`,
      source_refs: item.source_refs || (item.source ? [String(item.source.title || item.source.url || item.source.type || "数据库题库")] : []),
    },
    mode,
    fallback,
  );
}

function questionFromStart(
  start: {
    question_id: string;
    question: string;
    matched_skills: string[];
    source_refs: string[];
    tests?: Question["tests"];
  },
  mode: ModeId,
): Question {
  const fallback = questions.find((item) => item.id === start.question_id && item.mode === mode) || questions.find((item) => item.mode === mode);
  return backendQuestionToQuestion(
    {
      question_id: start.question_id,
      question: start.question,
      skills: start.matched_skills,
      source_refs: start.source_refs,
      tests: start.tests,
    },
    mode,
    fallback,
  );
}

function PracticePage() {
  const [searchParams] = useSearchParams();
  const [activeMode, setActiveMode] = useState<ModeId>("technical");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [question, setQuestion] = useState<Question>(questions[0]);
  const [nextQuestionData, setNextQuestionData] = useState<Question | null>(null);
  const [sessionCompleted, setSessionCompleted] = useState(false);
  const [sessionNotice, setSessionNotice] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [panelsSwapped, setPanelsSwapped] = useState(false);
  const [algorithmSubmitted, setAlgorithmSubmitted] = useState(false);
  const [feedback, setFeedback] = useState<BackendFeedback | null>(null);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [groupPaused, setGroupPaused] = useState(false);
  const [lastTurnId, setLastTurnId] = useState<string | null>(null);
  const [revisionOf, setRevisionOf] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<AlgorithmResult | null>(null);
  const [code, setCode] = useState(
    "def solution(s):\n    window = set()\n    left = 0\n    best = 0\n\n    for right, char in enumerate(s):\n        while char in window:\n            window.remove(s[left])\n            left += 1\n        window.add(char)\n        best = max(best, right - left + 1)\n\n    return best",
  );
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");
  const [modelOnline, setModelOnline] = useState(true);
  const mode = modeMeta.find((item) => item.id === activeMode) ?? modeMeta[0];
  const { Icon } = mode;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setSubmitted(false);
    setPanelsSwapped(false);
    setAlgorithmSubmitted(false);
    setFeedback(null);
    setConversation([]);
    setGroupPaused(false);
    setLastTurnId(null);
    setRevisionOf(null);
    setNextQuestionData(null);
    setSessionCompleted(false);
    setSessionNotice("");
    setAnswer("");
    setRunResult(null);
    const fallback = questions.find((item) => item.mode === activeMode) || questions[0];
    setQuestion(fallback);
    const savedProfile = loadUserProfile();
    const requestedSession = searchParams.get("session");
    const requestedRole = searchParams.get("role") || "后端开发工程师";
    const requestedJobId = searchParams.get("job_id") || undefined;
    const sessionRequest = requestedSession
      ? getSessionSummary(requestedSession)
      : startSession({
          mode: activeMode,
          role: requestedRole,
          job_id: requestedJobId,
          job_text: savedProfile.job_text || "Python FastAPI PostgreSQL Redis Docker 系统设计",
          user_profile: {
            ...savedProfile,
            skills: savedProfile.skills.length ? savedProfile.skills : ["Python", "FastAPI", "PostgreSQL"],
            projects: savedProfile.projects.length ? savedProfile.projects : ["TechMatch"],
          },
          difficulty: "medium",
        });
    Promise.allSettled([sessionRequest, healthCheck()]).then(([sessionResult, healthResult]) => {
      if (cancelled) return;
      if (sessionResult.status === "fulfilled") {
        const data = sessionResult.value;
        const persisted = (data as SessionSummary).session || data;
        setSessionId(String(persisted.session_id || data.session_id));
        const sessionMode = requestedSession ? (persisted.mode as ModeId) || activeMode : activeMode;
        if (requestedSession && sessionMode !== activeMode) {
          setActiveMode(sessionMode as ModeId);
        }
        const current = (persisted as SessionSummary).current_question as BackendQuestion | null | undefined;
        const initialQuestion = current ? backendQuestionToQuestion(current, sessionMode as ModeId, fallback) : questionFromStart(data as StartSessionResponse, sessionMode as ModeId);
        setQuestion(initialQuestion);
        setConversation([
          {
            id: `assistant-${initialQuestion.id}-${Date.now()}`,
            kind: "assistant",
            speaker: getModeLabel(sessionMode as ModeId),
            content: initialQuestion.prompt,
          },
        ]);
        setQuestionIndex(0);
      } else {
        setSessionId(null);
        setError("后端暂不可用，当前显示演示题；启动 FastAPI 后会自动联调。");
        setConversation([
          { id: `assistant-fallback-${Date.now()}`, kind: "assistant", speaker: mode.label, content: fallback.prompt },
        ]);
      }
      if (healthResult.status === "fulfilled") setModelOnline(Boolean(healthResult.value.status === "ok"));
      else setModelOnline(false);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [activeMode]);

  function changeMode(id: ModeId) {
    if (id !== activeMode) {
      setActiveMode(id);
      setQuestionIndex(0);
    }
  }
  async function finishSession() {
    if (!sessionId || completing) return;
    setCompleting(true);
    setError("");
    try {
      const result = await completeSession(sessionId);
      if (result.turn_count === 0) {
        setSessionCompleted(false);
        setSessionNotice("本次没有提交回答，未生成训练记录或报告。下次提交至少一轮回答后再结束训练即可。");
      } else {
        setSessionCompleted(true);
        setSessionNotice("");
      }
      setNextQuestionData(null);
    } catch {
      setError("结束训练失败，请稍后重试。");
    } finally {
      setCompleting(false);
    }
  }
  function nextQuestion(completeWhenDone = true) {
    const pendingQuestion = nextQuestionData;
    if (completeWhenDone && !pendingQuestion && sessionId) {
      void finishSession();
      return;
    }
    const fallback = questions.find((item) => item.mode === activeMode) || questions[0];
    const selectedQuestion = pendingQuestion || fallback;
    setQuestion(selectedQuestion);
    setNextQuestionData(null);
    setQuestionIndex((index) => index + 1);
    setSubmitted(false);
    setPanelsSwapped(false);
    setAlgorithmSubmitted(false);
    setFeedback(null);
    setRunResult(null);
    setAnswer("");
    if (!pendingQuestion && activeMode !== "algorithm") {
      setConversation((current) => [
        ...current,
        { id: `assistant-${selectedQuestion.id}-${Date.now()}`, kind: "assistant", speaker: mode.label, content: selectedQuestion.prompt },
      ]);
    }
  }
  function pauseGroupAndReply() {
    if (activeMode !== "group" || groupPaused || !submitted || !nextQuestionData) return;
    const pendingQuestion = nextQuestionData;
    setGroupPaused(true);
    setQuestion(pendingQuestion);
    setNextQuestionData(null);
    setQuestionIndex((index) => index + 1);
    setSubmitted(false);
    setPanelsSwapped(false);
    setRevisionOf(null);
    setAnswer("");
    setError("");
    // Keep the previous feedback visible on the right while the candidate
    // pauses the simulated participants and prepares a response.
  }
  function supplementAnswer() {
    if (!lastTurnId || !answer.trim()) return;
    setRevisionOf(lastTurnId);
    setSubmitted(false);
    setPanelsSwapped(false);
    setFeedback(null);
    setNextQuestionData(null);
    setError("");
    setAnswer((current) => `${current.trim()}\n\n补充回答：`);
  }
  async function submitAnswer() {
    if (answer.trim().length < 8 || !sessionId || submitting) return;
    const answerText = answer.trim();
    const wasRevision = Boolean(revisionOf);
    setSubmitting(true);
    setError("");
    try {
      const result = await submitTurn(sessionId, {
        question_id: question.id,
        answer_text: answer,
        revision_of: revisionOf || undefined,
        answer_mode: revisionOf ? "supplement" : "answer",
      });
      setFeedback(result.feedback);
      setSubmitted(true);
      if (activeMode === "group") setGroupPaused(false);
      setLastTurnId(result.turn_id);
      setRevisionOf(null);
      const next = result.next_question ? backendQuestionToQuestion(result.next_question, activeMode, question) : null;
      setNextQuestionData(next);
      setConversation((current) => {
        const messages: ConversationMessage[] = [
          ...current,
          { id: `user-${result.turn_id}`, kind: "user", speaker: "我", content: answerText },
        ];
        const reactions = result.feedback.group_reactions?.length
          ? result.feedback.group_reactions
          : result.feedback.group_reaction
            ? [result.feedback.group_reaction]
            : [];
        reactions.forEach((reaction, index) => {
          if (reaction.message) {
            messages.push({
              id: `peer-${result.turn_id}-${index}`,
              kind: "peer",
              speaker: reaction.speaker || `模拟队友 ${String.fromCharCode(65 + index)}`,
              role: reaction.role,
              content: reaction.message,
            });
          }
        });
        // A revision receives the same cursor; do not duplicate the current
        // prompt. In a group interview, participant messages appear before
        // the moderator's next prompt to preserve a natural chat sequence.
        if (next && (!wasRevision || next.id !== question.id)) {
          messages.push({ id: `assistant-${next.id}-${result.turn_id}`, kind: "assistant", speaker: mode.label, content: next.prompt });
        }
        return messages;
      });
      if (!result.next_question) setSessionCompleted(false);
    } catch (cause) {
      // If the browser lost the response after the server committed the turn,
      // reconcile from the persisted session before showing an error. This
      // prevents a transient disconnect from making users submit the same
      // answer again and hitting question_id_not_current.
      try {
        const persisted = await getSessionSummary(sessionId);
        const persistedTurn = [...(persisted.turns || [])].reverse().find((item) => String(item.question_id || "") === question.id && item.feedback);
        if (persistedTurn?.feedback) {
          setFeedback(persistedTurn.feedback as BackendFeedback);
          setSubmitted(true);
          setLastTurnId(String(persistedTurn.id || ""));
          setRevisionOf(null);
          const current = persisted.current_question as BackendQuestion | null | undefined;
          setNextQuestionData(current ? backendQuestionToQuestion(current, activeMode, question) : null);
          setError("");
          return;
        }
      } catch {
        // Preserve the original error below when reconciliation is unavailable.
      }
      const message = cause instanceof Error ? cause.message : "网络请求失败";
      setError(`提交失败：${message}。回答已保留在当前页面，可稍后重试。`);
    } finally {
      setSubmitting(false);
    }
  }
  async function runCode() {
    if (!sessionId || running) return;
    setRunning(true);
    setRunResult(null);
    setError("");
    try {
      const result = await runAlgorithm(sessionId, {
        question_id: question.id,
        code,
        language: "python",
        tests: question.tests || [],
      });
      setRunResult(result);
      // Persist the first code run as a turn so algorithm practice appears in
      // history/reports even though its UI uses the code panel instead of text feedback.
      if (!algorithmSubmitted) {
        const turn = await submitTurn(sessionId, {
          question_id: question.id,
          answer_text: `算法代码运行结果：${result.passed}/${result.total} 测试通过。`,
          code,
          language: "python",
          tests: question.tests || [],
        });
        setAlgorithmSubmitted(true);
        setNextQuestionData(turn.next_question ? backendQuestionToQuestion(turn.next_question, activeMode, question) : null);
      }
    } catch {
      setError("判题服务不可用，请确认后端和算法沙箱已启动。");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="practice-page">
      <section className="practice-header">
        <div>
          <span className="eyebrow">训练工作台</span>
          <h2>用一次短练习，校准你的回答。</h2>
          <p>选择场景后，系统会结合目标岗位和你的项目证据生成下一题。</p>
        </div>
        <div className="practice-header-actions">
          <div className="compact-status">
            <span className="status-dot" />
            {modelOnline ? "后端与模型服务在线" : "后端降级模式"}
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="重置当前训练"
            onClick={() => {
    setSubmitted(false);
    setLastTurnId(null);
    setRevisionOf(null);
              setPanelsSwapped(false);
    setFeedback(null);
              setAnswer("");
              setRunResult(null);
              setError("");
            }}
          >
            <RotateCcw size={17} />
          </button>
        </div>
      </section>
      {error ? (
        <div className="source-note" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>联调提示</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : null}
      {sessionCompleted ? (
        <div className="source-note" role="status">
          <CheckCircle2 size={16} />
          <div>
            <strong>本次训练已完成</strong>
            <p>报告已保存到训练历史，可以继续选择其他场景。</p>
          </div>
        </div>
      ) : null}
      {sessionNotice ? (
        <div className="source-note" role="status">
          <CircleHelp size={16} />
          <div>
            <strong>未生成训练记录</strong>
            <p>{sessionNotice}</p>
          </div>
        </div>
      ) : null}
      <section className="mode-switcher">
        {modeMeta.map((item) => {
          const ItemIcon = item.Icon;
          return (
            <button key={item.id} type="button" className={activeMode === item.id ? `mode-tab active tab-${item.color}` : "mode-tab"} onClick={() => changeMode(item.id)}>
              <ItemIcon size={16} />
              <span>{item.shortLabel}</span>
            </button>
          );
        })}
      </section>
      <section className="practice-meta">
        <div className="practice-meta-left">
          <span className={`mode-badge badge-${mode.color}`}>
            <Icon size={15} />
            {mode.label}
          </span>
          <span className="meta-divider" />
          <span>第 {questionIndex + 1} 题</span>
          <span className="meta-divider" />
          <span>建议用时 {activeMode === "stress" ? "30 秒" : activeMode === "algorithm" ? "20 分钟" : "5 分钟"}</span>
        </div>
        <div className="progress-meta">
          <span>训练进度</span>
          <div className="practice-progress">
            <span style={{ width: `${Math.min(22 + questionIndex * 12, 92)}%` }} />
          </div>
          <strong>{Math.min(22 + questionIndex * 12, 92)}%</strong>
        </div>
      </section>
      {activeMode !== "algorithm" && feedback ? (
        <div className="panel-layout-toolbar">
          <span>反馈已生成，可调整面板顺序</span>
          <button className="secondary-button panel-swap-button" type="button" onClick={() => setPanelsSwapped((swapped) => !swapped)} aria-pressed={panelsSwapped} title={panelsSwapped ? "恢复问题在左、反馈在右" : "交换问题和反馈面板"}>
            <ArrowLeftRight size={15} />
            {panelsSwapped ? "恢复默认顺序" : "交换面板"}
          </button>
        </div>
      ) : null}
      <div className={`${activeMode === "algorithm" ? "practice-grid algorithm-grid" : "practice-grid"}${panelsSwapped ? " panels-swapped" : ""}`}>
        {activeMode === "algorithm" ? (
        <div className="question-panel">
          <div className="question-panel-head">
            <div>
              <span className="eyebrow">问题 {question.id}</span>
              <h3>{loading ? "正在从后端准备题目..." : question.title}</h3>
            </div>
            <span className="difficulty-tag">难度 {question.difficulty}</span>
          </div>
          <p className="question-prompt">{question.prompt}</p>
          <div className="skill-tags">
            {question.skills.map((skill) => (
              <span key={skill}>{skill}</span>
            ))}
          </div>
          <div className="question-source">
            <ShieldCheck size={15} />
            <span>{question.source}</span>
            {question.sourceUrl ? (
              <a className="text-button" href={question.sourceUrl} target="_blank" rel="noreferrer">
                查看来源
              </a>
            ) : null}
            {question.sourceLicense ? <small>{question.sourceLicense}</small> : null}
            {question.sourceConfidence ? <small>可信度：{question.sourceConfidence}</small> : null}
            {question.sourceVersion ? <small>版本：{question.sourceVersion}</small> : null}
          </div>
          {activeMode !== "algorithm" ? (
            <>
              <label className="answer-label" htmlFor="answer">
                <span className="answer-label-title">{revisionOf ? "正在修改上一轮回答" : "你的回答"}</span>
                <span>{answer.length} 字</span>
              </label>
              {revisionOf ? (
                <div className="revision-notice" role="status">
                  <RotateCcw size={14} />
                  <span>当前正在修改上一轮回答，提交后会保留原回答并生成新的反馈。</span>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => {
                      setRevisionOf(null);
                      setAnswer("");
                    }}
                  >
                    取消修改
                  </button>
                </div>
              ) : null}
              <textarea id="answer" className="answer-input" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={activeMode === "stress" ? "先说结论，再给一个事实。注意控制在 30 秒内..." : "把你的思路写下来，系统会按当前场景的评分标准给出反馈..."} />
              <div className="answer-actions">
                <span>
                  <CircleHelp size={15} />
                  不确定时可以先写要点，提交后再看追问。
                </span>
                <button className="primary-button" type="button" disabled={answer.trim().length < 8 || !sessionId || submitting || submitted} onClick={submitAnswer}>
                  {submitting ? (
                    <>
                      <Gauge size={16} className="spin" />
                      分析中...
                    </>
                  ) : (
                    <>
                      <Send size={16} />
                      提交回答
                    </>
                  )}
                </button>
              </div>
            </>
          ) : null}
          {activeMode === "algorithm" ? (
            <div className="algorithm-question-footer">
              <div>
                <strong>判题约束</strong>
                <span>时间 O(n) · 空间 O(n) · Python 3.11 · 后端固定测试</span>
              </div>
              <div className="algorithm-actions">
                <button className="secondary-button" type="button" onClick={() => nextQuestion(false)}>
                  换一道题 <ArrowRight size={15} />
                </button>
                <button className="primary-button" type="button" onClick={() => void finishSession()} disabled={!sessionId || completing}>
                  {completing ? "保存报告中..." : "完成训练"}
                  <CheckCircle2 size={15} />
                </button>
              </div>
            </div>
          ) : null}
        </div>
        ) : (
          <ConversationPanel
            mode={mode.label}
            activeMode={activeMode}
            question={question}
            conversation={conversation}
            answer={answer}
            setAnswer={setAnswer}
            submitted={submitted}
            submitting={submitting}
            revisionOf={revisionOf}
            nextQuestionData={nextQuestionData}
            groupPaused={groupPaused}
            onToggleGroupPause={pauseGroupAndReply}
            onSubmit={submitAnswer}
            onNext={nextQuestion}
          />
        )}
        {activeMode === "algorithm" ? (
          <CodeEditor code={code} setCode={setCode} running={running} runResult={runResult} onRun={runCode} />
        ) : (
          <FeedbackPanel
            submitted={submitted || Boolean(feedback)}
            feedback={feedback}
            question={question}
            onRetry={() => {
              setSubmitted(false);
              setPanelsSwapped(false);
              setFeedback(null);
              if (lastTurnId) {
                setRevisionOf(lastTurnId);
              } else {
                setRevisionOf(null);
                setAnswer("");
              }
            }}
            onSupplement={lastTurnId ? supplementAnswer : undefined}
            onNext={nextQuestion}
          />
        )}
      </div>
    </div>
  );
}

function ConversationPanel({
  mode,
  activeMode,
  question,
  conversation,
  answer,
  setAnswer,
  submitted,
  submitting,
  revisionOf,
  nextQuestionData,
  groupPaused,
  onToggleGroupPause,
  onSubmit,
  onNext,
}: {
  mode: string;
  activeMode: ModeId;
  question: Question;
  conversation: ConversationMessage[];
  answer: string;
  setAnswer: (value: string) => void;
  submitted: boolean;
  submitting: boolean;
  revisionOf: string | null;
  nextQuestionData: Question | null;
  groupPaused: boolean;
  onToggleGroupPause: () => void;
  onSubmit: () => void;
  onNext: () => void;
}) {
  return (
    <section className={`conversation-panel ${activeMode === "group" ? "group-conversation" : ""}`}>
      <div className="conversation-head">
        <div>
          <span className="eyebrow">{activeMode === "group" ? "群面讨论" : "连续面试对话"}</span>
          <h3>{question.title}</h3>
          <small>{question.personalized ? "已结合岗位 JD 和你的简历生成" : `围绕一个选题展开多轮回答 · ${mode}`}</small>
        </div>
        {activeMode === "group" ? (
          <button
            className={`secondary-button group-pause-button ${groupPaused ? "active" : ""}`}
            type="button"
            onClick={onToggleGroupPause}
            disabled={groupPaused || !submitted || !nextQuestionData}
            aria-pressed={groupPaused}
          >
            {groupPaused ? "队友已暂停" : submitted && nextQuestionData ? "暂停并发言" : "等待你的回答"}
          </button>
        ) : null}
      </div>
      <div className="chat-thread" aria-live="polite">
        {conversation.map((message) => (
          <div className={`chat-message chat-message-${message.kind}`} key={message.id}>
            <div className="chat-avatar">{message.kind === "user" ? "我" : message.kind === "peer" ? message.speaker.slice(-1) : "AI"}</div>
            <div className="chat-message-body">
              <div className="chat-message-meta">
                <strong>{message.speaker}</strong>
                {message.role ? <span>{message.role}</span> : null}
              </div>
              <p>{message.content}</p>
            </div>
          </div>
        ))}
        {submitting ? (
          <div className="chat-typing"><span /> <span /> <span /> 模型正在整理下一步问题…</div>
        ) : null}
      </div>
      {activeMode !== "group" && nextQuestionData && submitted ? (
        <button className="chat-next-button" type="button" onClick={onNext}>
          <MessageSquareText size={15} /> 继续回答模型追问
        </button>
      ) : null}
      <div className="chat-composer">
        <div className="chat-composer-head">
          <label htmlFor="answer">{revisionOf ? "修改上一轮回答" : groupPaused && activeMode === "group" ? "暂停中，你的回应" : "你的回答"}</label>
          <span>{answer.length} 字</span>
        </div>
        {revisionOf ? <div className="revision-notice" role="status"><RotateCcw size={14} /><span>提交后会保留原回答，并生成新的反馈。</span></div> : null}
        <textarea
          id="answer"
          className="chat-input"
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          disabled={submitted || submitting}
          placeholder={activeMode === "group" ? "回应队友观点，推进讨论或提出新的判断依据…" : activeMode === "stress" ? "先说结论，再给一个事实。注意控制在 30 秒内…" : "继续回答当前问题，模型会在右侧给出建议并在中间追问…"}
        />
        <div className="chat-composer-actions">
          <span><CircleHelp size={14} /> {submitted ? "可在右侧选择修改或进入追问" : "回答提交后会保留在对话中"}</span>
          <button className="primary-button" type="button" disabled={answer.trim().length < 8 || submitted || submitting} onClick={onSubmit}>
            {submitting ? <><Gauge size={16} className="spin" /> 分析中…</> : <><Send size={16} /> 发送回答</>}
          </button>
        </div>
      </div>
    </section>
  );
}

function CodeEditor({ code, setCode, running, runResult, onRun }: { code: string; setCode: (value: string) => void; running: boolean; runResult: AlgorithmResult | null; onRun: () => void }) {
  const status = runResult?.status;
  return (
    <aside className="code-panel">
      <div className="code-panel-head">
        <div>
          <span className="eyebrow">代码编辑器</span>
          <h3>Python 3.11</h3>
        </div>
        <span className="sandbox-pill">
          <ShieldCheck size={13} />
          受限沙箱
        </span>
      </div>
      <div className="editor-wrap">
        <div className="line-numbers">
          {code.split("\n").map((_, index) => (
            <span key={index}>{index + 1}</span>
          ))}
        </div>
        <textarea aria-label="算法题代码" spellCheck={false} value={code} onChange={(event) => setCode(event.target.value)} />
      </div>
      <div className="test-status">
        {status === "passed" ? (
          <>
            <CheckCircle2 size={16} className="success-icon" />
            <span>
              {runResult?.passed} / {runResult?.total} 测试用例通过 · {Math.round(runResult?.runtime_ms || 0)}ms
            </span>
          </>
        ) : status === "failed" ? (
          <>
            <AlertCircle size={16} className="error-icon" />
            <span>
              {runResult?.passed} / {runResult?.total} 通过，请检查边界条件
            </span>
          </>
        ) : status === "timeout" ? (
          <>
            <AlertCircle size={16} className="error-icon" />
            <span>代码运行超时，已终止进程</span>
          </>
        ) : status === "rejected" ? (
          <>
            <AlertCircle size={16} className="error-icon" />
            <span>代码被安全策略拒绝</span>
          </>
        ) : (
          <>
            <CircleHelp size={16} />
            <span>提交前先运行固定测试用例</span>
          </>
        )}
      </div>
      <button className="primary-button full-button" type="button" onClick={onRun} disabled={running}>
        {running ? (
          <>
            <Gauge size={16} className="spin" />
            运行中...
          </>
        ) : (
          <>
            <Play size={16} />
            运行测试
          </>
        )}
      </button>
    </aside>
  );
}

const scoreLabel: Record<string, string> = {
  correctness: "正确性",
  complexity: "复杂度",
  tradeoff: "技术取舍",
  debugging: "故障排查",
  problem_understanding: "理解题意",
  algorithm: "算法思路",
  code_quality: "代码质量",
  star: "STAR 结构",
  ownership: "个人贡献",
  evidence: "证据",
  reflection: "复盘",
  stability: "稳定性",
  conciseness: "表达精炼",
  adaptability: "应变",
  decomposition: "问题拆解",
  metrics: "指标设计",
  hypothesis: "假设验证",
  validation: "验证方案",
  experiment: "实验设计",
  limitations: "局限性",
  critical_thinking: "批判性思维",
  motivation: "动机",
  fit: "岗位匹配",
  communication: "沟通",
  authenticity: "真实性",
  problem_framing: "问题框定",
  collaboration: "协作表达",
  consensus: "共识推动",
  time_management: "时间管理",
};

function FeedbackPanel({ submitted, feedback, question, onRetry, onSupplement, onNext }: { submitted: boolean; feedback: BackendFeedback | null; question: Question; onRetry: () => void; onSupplement?: () => void; onNext: () => void }) {
  const scoreEntries = feedback ? Object.entries(feedback.scores) : [];
  const average = scoreEntries.length ? Math.round((scoreEntries.reduce((sum, [, value]) => sum + Number(value), 0) / scoreEntries.length) * 20) : 0;
  const groupReactions = feedback?.group_reactions?.length ? feedback.group_reactions : feedback?.group_reaction ? [feedback.group_reaction] : [];
  return (
    <aside className={`feedback-panel ${submitted ? "feedback-visible" : ""}`}>
      <div className="feedback-head">
        <div>
          <span className="eyebrow">即时反馈</span>
          <h3>{submitted ? "这次回答，抓住了重点" : "提交后查看反馈"}</h3>
        </div>
        {submitted ? (
          <span className="score-badge">
            {average} <small>/100</small>
          </span>
        ) : (
          <span className="waiting-badge">
            <Clock3 size={14} />
            等待回答
          </span>
        )}
      </div>
      {submitted && feedback ? (
        <>
          <div className="score-bars">
            {scoreEntries.map(([key, value], index) => (
              <ScoreBar key={key} label={scoreLabel[key] || key} score={Math.round(Number(value) * 20)} color={["blue", "mint", "purple", "coral"][index % 4]} />
            ))}
          </div>
          <div className="feedback-section">
            <span className="feedback-label positive-label">
              <CheckCircle2 size={14} />
              做得好的地方
            </span>
            {(feedback.strengths || []).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          <div className="feedback-section">
            <span className="feedback-label improve-label">
              <AlertCircle size={14} />
              下一次可以更好
            </span>
            {(feedback.improvements || []).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          <div className="follow-up-card">
            <span>回答证据</span>
            <strong>{feedback.evidence_quotes?.[0] || "本次回答未提取到可引用证据。"}</strong>
          </div>
          {feedback.next_question || question.followUp ? (
            <div className="follow-up-card">
              <span>下一步追问</span>
              <strong>{feedback.next_question || question.followUp}</strong>
            </div>
          ) : null}
          {groupReactions.length ? (
            <div className="group-reaction-card">
              <div className="group-reaction-head">
                <span>模拟队友讨论{feedback.group_phase ? ` · ${feedback.group_phase}` : ""}</span>
                <strong>{groupReactions.length} 位队友</strong>
              </div>
              {groupReactions.map((reaction, index) => (
                <div className="group-reaction-message" key={`${reaction.speaker || "peer"}-${index}`}>
                  <div><strong>{reaction.speaker || `模拟队友 ${String.fromCharCode(65 + index)}`}</strong>{reaction.role ? <small>{reaction.role}</small> : null}</div>
                  <p>{reaction.message || "请回应队友观点并推动小组形成共识。"}</p>
                  {reaction.prompt ? <strong className="group-reaction-prompt">下一步：{reaction.prompt}</strong> : null}
                </div>
              ))}
            </div>
          ) : null}
          <div className="feedback-actions">
            <button className="secondary-button" type="button" onClick={onRetry}>
              {onSupplement ? "重新回答" : "重新回答"}
            </button>
            {onSupplement ? (
              <button className="secondary-button" type="button" onClick={onSupplement}>
                补充/修订
              </button>
            ) : null}
            <button className="primary-button" type="button" onClick={onNext}>
              下一题 <ArrowRight size={15} />
            </button>
          </div>
        </>
      ) : (
        <div className="feedback-empty">
          <div className="empty-illustration">
            <Sparkles size={22} />
          </div>
          <p>系统会按当前场景的 Rubric 评分，并保留你的原句证据。</p>
          <span>相关性 · 证据 · 结构 · 表达</span>
        </div>
      )}
    </aside>
  );
}

function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="score-bar-row">
      <span>{label}</span>
      <div className="score-bar">
        <span className={`fill-${color}`} style={{ width: `${score}%` }} />
      </div>
      <strong>{score}</strong>
    </div>
  );
}

type MaterialDraft = {
  full_name: string;
  headline: string;
  summary: string;
  education: string;
  experience: string;
  skills: string;
  projects: string;
  achievements: string;
  title: string;
  company: string;
  role: string;
  location: string;
  seniority: string;
  responsibilities: string;
  requirements: string;
};

const emptyMaterialDraft: MaterialDraft = {
  full_name: "",
  headline: "",
  summary: "",
  education: "",
  experience: "",
  skills: "",
  projects: "",
  achievements: "",
  title: "",
  company: "",
  role: "",
  location: "",
  seniority: "",
  responsibilities: "",
  requirements: "",
};

function textValue(value: unknown) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function listValue(value: unknown) {
  if (Array.isArray(value))
    return value
      .map((item) => textValue(item))
      .filter(Boolean)
      .join("\n");
  return textValue(value);
}

function documentId(document: CandidateDocument) {
  return String(document.id || document.document_id || "");
}

function draftFromDocument(document: CandidateDocument | null, kind: DocumentKind): MaterialDraft {
  if (!document) return { ...emptyMaterialDraft };
  const parsed = (document.parsed_json || document.parsed || {}) as Record<string, unknown>;
  const profile = (parsed.profile || parsed.resume || {}) as Record<string, unknown>;
  const job = (parsed.job || parsed.job_description || {}) as Record<string, unknown>;
  if (kind === "resume") {
    return {
      ...emptyMaterialDraft,
      full_name: textValue(profile.full_name || profile.name || parsed.full_name),
      headline: textValue(profile.headline || profile.target_role),
      summary: textValue(profile.summary),
      education: textValue(profile.education),
      experience: textValue(profile.experience || profile.work_experience),
      skills: listValue(profile.skills),
      projects: listValue(profile.projects),
      achievements: listValue(profile.achievements || profile.results),
    };
  }
  return {
    ...emptyMaterialDraft,
    title: textValue(job.title || parsed.title),
    company: textValue(job.company || parsed.company),
    role: textValue(job.role),
    location: textValue(job.location),
    seniority: textValue(job.seniority || job.level),
    summary: textValue(job.summary),
    skills: listValue(job.skills),
    responsibilities: listValue(job.responsibilities),
    requirements: listValue(job.requirements),
  };
}

function MaterialsPage() {
  const navigate = useNavigate();
  const [kind, setKind] = useState<DocumentKind>("resume");
  const [documents, setDocuments] = useState<CandidateDocument[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<MaterialDraft>({ ...emptyMaterialDraft });
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = documents.find((item) => documentId(item) === selectedId) || null;
  const visibleDocuments = documents.filter((item) => item.kind === kind);

  useEffect(() => {
    let cancelled = false;
    void listDocuments()
      .then((items) => {
        if (cancelled) return;
        setDocuments(items);
        const first = items.find((item) => item.kind === kind) || items[0];
        if (first) {
          setSelectedId(documentId(first));
          setKind(first.kind);
          setDraft(draftFromDocument(first, first.kind));
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "资料服务暂不可用");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const next = documents.find((item) => documentId(item) === selectedId && item.kind === kind);
    if (next) setDraft(draftFromDocument(next, kind));
    else if (!visibleDocuments.length) setDraft({ ...emptyMaterialDraft });
  }, [selectedId, kind, documents.length]);

  function switchKind(nextKind: DocumentKind) {
    setKind(nextKind);
    setError("");
    setNotice("");
    const next = documents.find((item) => item.kind === nextKind);
    setSelectedId(next ? documentId(next) : "");
    setDraft(draftFromDocument(next || null, nextKind));
  }

  async function handleUpload(file: File) {
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const uploaded = await uploadDocument(file, kind);
      const uploadedId = documentId(uploaded);
      setDocuments((current) => [uploaded, ...current.filter((item) => documentId(item) !== uploadedId)]);
      setSelectedId(uploadedId);
      setDraft(draftFromDocument(uploaded, kind));
      setNotice("文件已上传，AI 正在提取内容。请校对后再保存到档案。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文件上传失败，请稍后重试");
    } finally {
      setUploading(false);
    }
  }

  function updateField(field: keyof MaterialDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function saveDraft() {
    if (!selected) {
      setError("请先上传一份文件");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (kind === "resume") {
        const profile = {
          ...loadUserProfile(),
          full_name: draft.full_name.trim(),
          headline: draft.headline.trim(),
          summary: draft.summary.trim(),
          education: draft.education.trim(),
          experience: draft.experience.trim(),
          skills: draft.skills
            .split(/[,，\n]/)
            .map((item) => item.trim())
            .filter(Boolean),
          projects: draft.projects
            .split(/\n+/)
            .map((item) => item.trim())
            .filter(Boolean),
          achievements: draft.achievements
            .split(/\n+/)
            .map((item) => item.trim())
            .filter(Boolean),
        };
        await confirmDocument(documentId(selected), {
          parsed: { kind, profile },
        });
        await saveUserProfile(profile);
      } else {
        const job = {
          title: draft.title.trim(),
          company: draft.company.trim(),
          role: draft.role.trim(),
          location: draft.location.trim(),
          seniority: draft.seniority.trim(),
          summary: draft.summary.trim(),
          skills: draft.skills
            .split(/[,，\n]/)
            .map((item) => item.trim())
            .filter(Boolean),
          responsibilities: draft.responsibilities
            .split(/\n+/)
            .map((item) => item.trim())
            .filter(Boolean),
          requirements: draft.requirements
            .split(/\n+/)
            .map((item) => item.trim())
            .filter(Boolean),
        };
        await confirmDocument(documentId(selected), { parsed: { kind, job } });
      }
      setDocuments((current) => current.map((item) => (documentId(item) === documentId(selected) ? { ...item, status: "confirmed" } : item)));
      setNotice(kind === "resume" ? "简历已保存到个人档案。" : "JD 已保存，可前往岗位匹配查看结果。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  }

  async function removeSelected() {
    if (!selected || !documentId(selected)) return;
    if (!globalThis.confirm(`确定删除 ${selected.filename}？`)) return;
    setError("");
    try {
      await deleteDocument(documentId(selected));
      const remaining = documents.filter((item) => documentId(item) !== documentId(selected));
      setDocuments(remaining);
      const next = remaining.find((item) => item.kind === kind);
      setSelectedId(next ? documentId(next) : "");
      setDraft(draftFromDocument(next || null, kind));
      setNotice("资料已删除。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败，请稍后重试");
    }
  }

  const fields: Array<{
    key: keyof MaterialDraft;
    label: string;
    multiline?: boolean;
    hint?: string;
  }> =
    kind === "resume"
      ? [
          { key: "full_name", label: "姓名" },
          { key: "headline", label: "求职方向" },
          { key: "summary", label: "个人简介", multiline: true },
          { key: "education", label: "教育背景", multiline: true },
          { key: "experience", label: "工作 / 实习经历", multiline: true },
          {
            key: "skills",
            label: "技能",
            multiline: true,
            hint: "用逗号或换行分隔",
          },
          {
            key: "projects",
            label: "项目经历",
            multiline: true,
            hint: "每行一段经历",
          },
          {
            key: "achievements",
            label: "关键成果",
            multiline: true,
            hint: "每行一项结果或指标",
          },
        ]
      : [
          { key: "title", label: "岗位名称" },
          { key: "company", label: "公司" },
          { key: "role", label: "岗位方向" },
          { key: "location", label: "工作地点" },
          { key: "seniority", label: "职级" },
          { key: "summary", label: "岗位简介", multiline: true },
          {
            key: "skills",
            label: "核心技能",
            multiline: true,
            hint: "用逗号或换行分隔",
          },
          {
            key: "responsibilities",
            label: "工作职责",
            multiline: true,
            hint: "每行一项职责",
          },
          {
            key: "requirements",
            label: "任职要求",
            multiline: true,
            hint: "每行一项要求",
          },
        ];

  return (
    <div className="materials-page">
      <section className="page-intro materials-intro">
        <div>
          <span className="eyebrow">求职资料</span>
          <h2>统一管理简历与目标岗位。</h2>
          <p>上传文件后由强模型提取关键信息，你可以校对每个字段，再保存到个人档案和岗位库。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => navigate("/match")}>
          <Target size={16} /> 查看岗位匹配
        </button>
      </section>
      {error ? (
        <div className="source-note materials-alert" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>资料服务提示</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : null}
      {notice ? (
        <div className="materials-notice" role="status">
          <CheckCircle2 size={16} /> {notice}
        </div>
      ) : null}
      <div className="materials-layout">
        <aside className="materials-library panel">
          <div className="panel-title-row">
            <div>
              <span className="eyebrow">资料库</span>
              <h3>我的求职文件</h3>
            </div>
            <FileCheck2 size={17} className="muted-icon" />
          </div>
          <div className="material-tabs" role="tablist" aria-label="资料类型">
            <button className={kind === "resume" ? "material-tab active" : "material-tab"} type="button" onClick={() => switchKind("resume")}>
              <FileText size={15} /> 简历
            </button>
            <button className={kind === "job_description" ? "material-tab active" : "material-tab"} type="button" onClick={() => switchKind("job_description")}>
              <BriefcaseBusiness size={15} /> JD
            </button>
          </div>
          <div className="materials-file-list">
            {loading ? <div className="materials-empty">正在加载资料…</div> : null}
            {!loading && !visibleDocuments.length ? (
              <div className="materials-empty">
                还没有{kind === "resume" ? "简历" : "JD"}
                <span>上传文件后会出现在这里</span>
              </div>
            ) : null}
            {visibleDocuments.map((item) => {
              const id = documentId(item);
              return (
                <button
                  key={id || item.filename}
                  className={id === selectedId ? "material-file selected" : "material-file"}
                  type="button"
                  onClick={() => {
                    setSelectedId(id);
                    setDraft(draftFromDocument(item, kind));
                  }}
                >
                  <span className="material-file-icon">
                    <FileText size={16} />
                  </span>
                  <span className="material-file-copy">
                    <strong>{item.filename}</strong>
                    <small>{item.status === "confirmed" ? "已确认" : item.status === "failed" ? "解析失败" : "待校对"}</small>
                  </span>
                  <ArrowRight size={14} />
                </button>
              );
            })}
          </div>
        </aside>
        <section className="materials-editor">
          <div className="upload-panel panel">
            <div className="upload-copy">
              <span className="upload-icon">
                <UploadCloud size={20} />
              </span>
              <div>
                <strong>上传{kind === "resume" ? "简历" : "岗位 JD"}</strong>
                <p>支持 PDF、DOCX、TXT、MD，单文件不超过 5 MB</p>
              </div>
            </div>
            <label className="secondary-button upload-button">
              {uploading ? <RotateCcw size={15} className="spin" /> : <Plus size={15} />}
              {uploading ? "解析中…" : "选择文件"}
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.currentTarget.value = "";
                  if (file) void handleUpload(file);
                }}
                disabled={uploading}
              />
            </label>
          </div>
          <div className="materials-form-panel panel">
            <div className="panel-title-row materials-form-heading">
              <div>
                <span className="eyebrow">AI 提取结果</span>
                <h3>{selected ? selected.filename : `等待上传${kind === "resume" ? "简历" : "JD"}`}</h3>
              </div>
              {selected ? <span className={selected.status === "confirmed" ? "small-tag green-tag" : "small-tag blue-tag"}>{selected.status === "confirmed" ? "已确认" : "需要校对"}</span> : null}
            </div>
            {selected ? (
              <div className="ai-review-note">
                <Sparkles size={15} />
                <span>强模型仅根据文件内容填充，空白字段代表未识别到信息。保存前请人工核对。</span>
              </div>
            ) : null}
            {!selected ? (
              <div className="materials-empty materials-editor-empty">
                <FileText size={28} />
                <p>上传一份文件开始整理</p>
                <span>解析结果会在这里展示并支持编辑</span>
              </div>
            ) : null}
            {selected ? (
              <div className="materials-fields">
                {fields.map((field) => (
                  <label className="material-field" key={field.key}>
                    <span>
                      {field.label}
                      {field.hint ? <small>{field.hint}</small> : null}
                    </span>
                    {field.multiline ? <textarea rows={field.key === "summary" ? 3 : 4} value={draft[field.key]} onChange={(event) => updateField(field.key, event.target.value)} /> : <input value={draft[field.key]} onChange={(event) => updateField(field.key, event.target.value)} />}
                  </label>
                ))}
              </div>
            ) : null}
            {selected ? (
              <div className="materials-form-actions">
                <button className="text-button danger-text" type="button" onClick={() => void removeSelected()}>
                  <Trash2 size={15} /> 删除资料
                </button>
                <button className="primary-button" type="button" onClick={() => void saveDraft()} disabled={saving}>
                  {saving ? "保存中…" : "确认并保存到档案"} <Check size={15} />
                </button>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function MatchPage() {
  const navigate = useNavigate();
  const [selectedRoleKey, setSelectedRoleKey] = useState("");
  const [jobs, setJobs] = useState<
    Array<{
      id?: string;
      job_id?: string;
      name?: string;
      title?: string;
      role?: string;
      company?: string;
      jd_text?: string;
      job_text?: string;
      skills?: string[];
    }>
  >([]);
  const [profile, setProfile] = useState<UserProfile>(() => loadUserProfile());
  const [match, setMatch] = useState<MatchResponse | null>(null);
  const [matchScores, setMatchScores] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const latestMatchRequest = useRef(0);
  const jobName = (job: (typeof jobs)[number]) => job.title || job.name || job.role || "未命名岗位";
  const jobKey = (job: (typeof jobs)[number], index: number) => String(job.id || job.job_id || `${jobName(job)}-${index}`);
  const roles = jobs.map((job, index) => ({
    id: job.id || job.job_id,
    key: jobKey(job, index),
    name: jobName(job),
    company: job.company || "已保存岗位",
    fallbackSkills: job.skills?.length ? job.skills : [],
    jd_text: job.jd_text || job.job_text || "",
  }));
  const role = roles.find((item) => item.key === selectedRoleKey) ?? roles[0];
  const matchedSkills = match ? (Array.isArray(match.profile_matched_skills) ? match.profile_matched_skills : match.matched_skills || []) : [];
  const requiredSkills = match?.required_skills?.length ? match.required_skills : role?.fallbackSkills || [];
  const gapSkills = requiredSkills.filter((skill) => !matchedSkills.includes(skill));

  function scoreForRole(item: (typeof roles)[number]) {
    return matchScores[item.key];
  }

  const currentScore = role ? scoreForRole(role) : undefined;

  useEffect(() => {
    // Materials confirmation publishes this event after the server profile is
    // updated. Re-read the profile and jobs so the score input hash changes and
    // the API creates a fresh snapshot for every confirmed resume revision.
    const refreshAfterMaterialsUpdate = () => {
      setProfile(loadUserProfile());
      setMatch(null);
      setMatchScores({});
      void listJobs()
        .then((result) => {
          setJobs(result);
          if (!result.length) {
            setSelectedRoleKey("");
            return;
          }
          setSelectedRoleKey((current) => (result.some((job, index) => jobKey(job, index) === current) ? current : jobKey(result[0], 0)));
        })
        .catch(() => {
          // The next regular refresh/retry will surface a visible error.
        });
    };
    return subscribeWorkspaceUpdates(refreshAfterMaterialsUpdate);
  }, []);

  async function refreshMatch(target = role) {
    if (!target) return;
    const requestRoleKey = target.key;
    const requestId = ++latestMatchRequest.current;
    setLoading(true);
    setError("");
    setMatch(null);
    try {
      const result = await previewMatch({
        mode: "technical",
        role: target.name,
        job_id: target.id,
        job_text: target.jd_text,
        user_profile: profile,
        difficulty: "medium",
      });
      if (latestMatchRequest.current !== requestId) return;
      setMatch(result);
      if (Number.isFinite(Number(result.match_score))) {
        setMatchScores((scores) => ({
          ...scores,
          [requestRoleKey]: Number(result.match_score),
        }));
      }
    } catch (cause) {
      if (latestMatchRequest.current !== requestId) return;
      setMatch(null);
      setError(cause instanceof Error ? cause.message : "岗位匹配服务暂不可用，已显示本地建议。");
    } finally {
      if (latestMatchRequest.current === requestId) setLoading(false);
    }
  }
  useEffect(() => {
    let cancelled = false;
    void listJobs()
      .then((result) => {
        if (cancelled) return;
        setJobs(result);
        if (result.length) {
          const first = result[0];
          setSelectedRoleKey((current) => (result.some((job, index) => jobKey(job, index) === current) ? current : jobKey(first, 0)));
        } else {
          setSelectedRoleKey("");
          setMatch(null);
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "岗位列表加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (role) void refreshMatch();
  }, [selectedRoleKey, jobs, profile]);
  return (
    <div className="match-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">岗位匹配</span>
          <h2>把个人经历，映射到真实岗位。</h2>
          <p>系统会结合已确认的 JD、简历和真实题库，生成可追溯的匹配评分和个性化训练题。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => navigate("/materials")}>
          <FolderOpen size={16} />
          管理求职资料
        </button>
      </section>
      {error ? (
        <div className="source-note" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>匹配服务提示</strong>
            <p>
              {error}{" "}
              <button className="text-button" type="button" onClick={() => void refreshMatch()}>
                重试
              </button>
            </p>
          </div>
        </div>
      ) : null}
      <div className="match-layout">
        <aside className="role-list-panel">
          <div className="panel-title-row">
            <div>
              <span className="eyebrow">已保存岗位</span>
              <h3>{roles.length} 个目标岗位</h3>
            </div>
            <Search size={16} className="muted-icon" />
          </div>
          <div className="role-list">
            {roles.map((item) => {
              const itemScore = scoreForRole(item);
              return (
                <button
                  key={item.key}
                  type="button"
                  className={selectedRoleKey === item.key ? "role-list-item selected" : "role-list-item"}
                  onClick={() => {
                    if (item.key === selectedRoleKey) return;
                    setMatch(null);
                    setSelectedRoleKey(item.key);
                  }}
                >
                  <span className={`role-score ${itemScore === undefined ? "score-unrated" : `score-${itemScore >= 75 ? "high" : itemScore >= 50 ? "mid" : "low"}`}`}>{itemScore ?? "—"}</span>
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.company}</small>
                  </span>
                  <ArrowRight size={15} />
                </button>
              );
            })}
            {!roles.length && !loading ? <p className="role-list-empty">还没有保存的岗位 JD</p> : null}
          </div>
          <button className="role-add-button" type="button" onClick={() => navigate("/materials")}>
            <Plus size={15} />
            上传新的 JD
          </button>
        </aside>
        {role ? <div className="match-detail">
          <div className="match-detail-top">
            <div>
              <span className="eyebrow">当前匹配结果</span>
              <h3>{role.name}</h3>
              <p>
                {role.company} · {loading ? "正在生成固定评分…" : match ? "评分已固定" : "等待评分"}
              </p>
            </div>
            <button className="primary-button" type="button" onClick={() => navigate(`/practice?role=${encodeURIComponent(role.name)}${role.id ? `&job_id=${encodeURIComponent(role.id)}` : ""}`)}>
              <Sparkles size={16} />
              用此岗位开始训练
            </button>
          </div>
          <div className="match-score-grid">
            <div className="match-score-card">
              <span className="eyebrow">综合匹配度</span>
              <div className="large-score">
                <strong>{loading ? "—" : currentScore ?? "—"}</strong>
                <span>/100</span>
              </div>
              <div className="score-caption">
                <span className="status-dot" />
                {match?.score_source === "strong_model" ? "大模型结合 JD 与简历评分" : "按 JD 与简历技能覆盖评分"}
              </div>
            </div>
            <div className="match-explanation">
              <div className="explanation-icon">
                <GitBranch size={19} />
              </div>
              <div>
                <strong>为什么匹配</strong>
                <p>{match?.score_explanation || "评分只在简历或 JD 内容变化后重新生成，切换页面和重复点击不会改变结果。"}</p>
                <div className="source-line">
                  <ShieldCheck size={14} />
                  {match?.score_cached ? "已读取持久化评分快照" : "评分快照已保存到数据库"}
                </div>
              </div>
            </div>
          </div>
          <div className="skill-matrix">
            <div className="section-heading">
              <div>
                <span className="eyebrow">技能覆盖</span>
                <h3>优势与补强方向</h3>
              </div>
            </div>
            <div className="skill-columns">
              <div className="skill-column">
                <span className="column-label success-label">
                  <CheckCircle2 size={15} />
                  已覆盖技能
                </span>
                <div className="skill-chip-list">
                  {matchedSkills.map((skill, index) => (
                    <div className="skill-chip covered" key={skill}>
                      <span>{skill}</span>
                      <strong>{index === 0 ? "核心匹配" : "已覆盖"}</strong>
                    </div>
                  ))}
                  {!matchedSkills.length ? <div className="skill-chip-empty">暂无明确覆盖技能</div> : null}
                </div>
              </div>
              <div className="skill-column">
                <span className="column-label warning-label">
                  <AlertCircle size={15} />
                  建议补强
                </span>
                <div className="skill-chip-list">
                  {(match?.score_gaps?.length ? match.score_gaps : gapSkills).map((skill) => (
                    <div className="skill-chip gap" key={skill}>
                      <span>{skill}</span>
                      <button type="button" onClick={() => navigate("/practice")} aria-label={`训练 ${skill}`}>
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  ))}
                  {!(match?.score_gaps?.length || gapSkills.length) ? <div className="skill-chip-empty">暂无明确技能缺口</div> : null}
                </div>
              </div>
            </div>
          </div>
          {match?.questions?.length ? (
            <div className="personalized-question-section">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">题目推荐</span>
                  <h3>{match.question_generation_source === "strong_model" ? "结合你的背景生成" : "从真实题库召回"}</h3>
                </div>
                <span className="question-generation-badge">
                  {match.question_generation_source === "strong_model" ? "强模型个性化" : "真实题库"}
                </span>
              </div>
              <div className="personalized-question-list">
                {match.questions.slice(0, 5).map((item, index) => (
                  <div className="personalized-question-item" key={`${item.question_id}-${index}`}>
                    <span className="personalized-question-index">{index + 1}</span>
                    <div>
                      <strong>{item.question}</strong>
                      <small>
                        {item.personalized && item.personalization_basis?.length
                          ? `依据：${item.personalization_basis.join("、")}`
                          : `考察：${(item.skills || []).join("、") || "岗位通用能力"}`}
                      </small>
                      {item.source_refs?.length ? <small>来源：{item.source_refs[0]}</small> : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="match-trace">
            <div className="trace-step done">
              <span>
                <Check size={14} />
              </span>
              <div>
                <strong>JD 解析</strong>
                <small>{role.jd_text.trim() ? "已保存岗位描述" : "等待 JD"}</small>
              </div>
            </div>
            <div className="trace-line done-line" />
            <div className="trace-step done">
              <span>
                <Check size={14} />
              </span>
              <div>
                <strong>技能归一化</strong>
                <small>{matchedSkills.length} 个图谱节点</small>
              </div>
            </div>
            <div className="trace-line" />
            <div className="trace-step active">
              <span>3</span>
              <div>
                <strong>训练验证</strong>
                <small>{match?.questions?.length || 0} 道题目可用于训练</small>
              </div>
            </div>
          </div>
        </div> : (
          <div className="match-detail match-empty-detail">
            <div className="empty-illustration"><FileText size={22} /></div>
            <h3>先保存一份真实岗位 JD</h3>
            <p>系统不会再用演示岗位生成伪匹配分。上传并确认 JD 后，才会结合已确认简历生成固定评分。</p>
            <button className="primary-button" type="button" onClick={() => navigate("/materials")}>上传岗位 JD <ArrowRight size={15} /></button>
          </div>
        )}
      </div>
    </div>
  );
}

function QuestionBankPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"all" | ModeId>("all");
  const [items, setItems] = useState<Question[]>([]);
  const [selected, setSelected] = useState<Question | null>(null);
  const [favorites, setFavorites] = useState<string[]>(() => loadFavorites());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [joining, setJoining] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listKnowledgeItems({
        limit: 300,
        processType: mode === "all" ? undefined : mode,
        query,
      });
      const mapped = result.map(questionFromKnowledge);
      setItems(mapped.length ? mapped : questions);
      setSelected((current) => (current && mapped.some((item) => item.id === current.id) ? current : mapped[0] || questions[0]));
    } catch (cause) {
      setItems(questions);
      setSelected((current) => current || questions[0]);
      setError(cause instanceof Error ? `${cause.message}，当前显示演示题库。` : "题库服务暂不可用，当前显示演示题库。");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    const timer = globalThis.setTimeout(
      () => {
        void load();
      },
      query ? 250 : 0,
    );
    return () => globalThis.clearTimeout(timer);
  }, [query, mode]);
  useEffect(() => {
    let cancelled = false;
    void listFavorites()
      .then((result) => {
        if (!cancelled) setFavorites(result.ids);
      })
      .catch(() => {
        /* local favorites remain usable */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const filtered = items.filter((item) => (mode === "all" || item.mode === mode) && `${item.title}${item.prompt}${item.skills.join("")}${item.source}`.toLowerCase().includes(query.toLowerCase()));
  async function favorite() {
    if (!selected) return;
    try {
      const next = await toggleFavorite(selected.id);
      setFavorites(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "收藏失败，请稍后重试。");
    }
  }
  async function addToTraining() {
    if (!selected) return;
    setJoining(true);
    setError("");
    try {
      const profile = loadUserProfile();
      const session = await startSession({
        mode: selected.mode,
        role: selected.backend?.role || "后端开发工程师",
        job_text: profile.job_text || "Python FastAPI PostgreSQL Redis Docker 系统设计",
        user_profile: profile,
        difficulty: selected.difficulty === "高" || selected.difficulty === "hard" ? "hard" : selected.difficulty === "低" ? "easy" : "medium",
      });
      if (selected.backend) queueQuestion(selected.backend);
      navigate(`/practice?session=${encodeURIComponent(session.session_id)}&question=${encodeURIComponent(session.question_id)}`);
    } catch (cause) {
      setError(cause instanceof Error ? `${cause.message}，无法创建训练会话。` : "创建训练会话失败，请重试。");
    } finally {
      setJoining(false);
    }
  }
  return (
    <div className="question-bank-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">题库</span>
          <h2>按岗位和场景，挑一道真正有用的题。</h2>
          <p>题目会带着技能、Rubric 和来源进入训练，不只是一个问题列表。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => setError("提交题目需要登录后开放，当前可先将题目加入训练。")}>
          <Plus size={16} />
          提交题目
        </button>
      </section>
      {error ? (
        <div className="source-note" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>题库提示</strong>
            <p>
              {error}{" "}
              <button className="text-button" type="button" onClick={() => void load()}>
                重试
              </button>
            </p>
          </div>
        </div>
      ) : null}
      <div className="question-bank-layout">
        <section className="question-list-panel">
          <div className="search-row">
            <div className="search-input">
              <Search size={17} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索题目、技能或岗位..." />
            </div>
            <button className="filter-button" type="button" onClick={() => setMode("all")}>
              <SlidersIcon />
              筛选
            </button>
          </div>
          <div className="filter-tabs">
            {[
              { id: "all", label: "全部" },
              ...modeMeta.map((item) => ({
                id: item.id,
                label: item.shortLabel,
              })),
            ].map((item) => (
              <button key={item.id} type="button" className={mode === item.id ? "filter-tab active" : "filter-tab"} onClick={() => setMode(item.id as "all" | ModeId)}>
                {item.label}
              </button>
            ))}
          </div>
          {loading ? (
            <div className="empty-list">
              <Gauge size={22} className="spin" />
              <p>正在从数据库加载题库…</p>
            </div>
          ) : (
            <div className="question-list">
              {filtered.map((item) => (
                <button key={item.id} type="button" className={selected?.id === item.id ? "question-list-item selected" : "question-list-item"} onClick={() => setSelected(item)}>
                  <div className={`question-list-icon question-icon-${item.mode}`}>
                    <ModeIcon mode={item.mode} />
                  </div>
                  <div className="question-list-copy">
                    <div>
                      <strong>{item.title}</strong>
                      <span className="difficulty-tag">{item.difficulty}</span>
                      {favorites.includes(item.id) ? <span className="small-tag green-tag">已收藏</span> : null}
                    </div>
                    <p>{item.prompt}</p>
                    <div className="question-list-meta">
                      <span>{getModeLabel(item.mode)}</span>
                      <span>·</span>
                      <span>{item.skills.join(" / ") || "通用能力"}</span>
                    </div>
                  </div>
                  <ArrowRight size={15} className="muted-icon" />
                </button>
              ))}
              {filtered.length === 0 ? (
                <div className="empty-list">
                  <CircleHelp size={22} />
                  <p>没有找到匹配题目，换个关键词试试。</p>
                </div>
              ) : null}
            </div>
          )}
        </section>
        {selected ? (
          <aside className="question-detail-panel">
            <div className="detail-top">
              <span className={`mode-badge badge-${modeMeta.find((item) => item.id === selected.mode)?.color ?? "blue"}`}>
                <ModeIcon mode={selected.mode} />
                {getModeLabel(selected.mode)}
              </span>
              <button className={favorites.includes(selected.id) ? "icon-button active" : "icon-button"} type="button" aria-label="收藏题目" onClick={() => void favorite()}>
                <BookOpen size={17} />
              </button>
            </div>
            <h3>{selected.title}</h3>
            <p className="detail-prompt">{selected.prompt}</p>
            <div className="detail-section">
              <span className="feedback-label">考察技能</span>
              <div className="skill-tags">
                {selected.skills.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))}
              </div>
            </div>
            <div className="detail-section">
              <span className="feedback-label">评分要点</span>
              <div className="rubric-list">
                {selected.rubric.map((item) => (
                  <div key={item}>
                    <CheckCircle2 size={15} />
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="detail-source">
              <ShieldCheck size={15} />
              <span>{selected.source}</span>
              {selected.sourceUrl ? (
                <a href={selected.sourceUrl} target="_blank" rel="noreferrer" className="text-button">
                  来源链接
                </a>
              ) : null}
              {selected.sourceLicense ? <small>{selected.sourceLicense}</small> : null}
              {selected.sourceConfidence ? <small>可信度：{selected.sourceConfidence}</small> : null}
              {selected.sourceVersion ? <small>版本：{selected.sourceVersion}</small> : null}
            </div>
            <button className="primary-button full-button" type="button" onClick={() => void addToTraining()} disabled={joining}>
              {joining ? (
                <>
                  <Gauge size={16} className="spin" />
                  创建会话中...
                </>
              ) : (
                <>
                  加入训练 <ArrowRight size={16} />
                </>
              )}
            </button>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function SlidersIcon() {
  return <SlidersHorizontal size={16} />;
}

function ModeIcon({ mode }: { mode: ModeId }) {
  const ItemIcon = modeMeta.find((item) => item.id === mode)?.Icon ?? CircleHelp;
  return <ItemIcon size={16} />;
}
function getModeLabel(mode: ModeId) {
  return modeMeta.find((item) => item.id === mode)?.label ?? mode;
}

function ReportsPage() {
  const [history, setHistory] = useState<SessionSummary[]>([]);
  const [reports, setReports] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [expandedSession, setExpandedSession] = useState<SessionSummary | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [historyData, reportData] = await Promise.all([listSessionHistory(), listReports()]);
      setHistory(historyData);
      setReports(reportData);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "报告服务暂不可用，请重试。");
    } finally {
      setLoading(false);
    }
  };
  async function toggleDetails(sessionId: string) {
    if (expandedSessionId === sessionId) {
      setExpandedSessionId(null);
      setExpandedSession(null);
      setDetailsError("");
      return;
    }
    setExpandedSessionId(sessionId);
    setExpandedSession(null);
    setDetailsLoading(true);
    setDetailsError("");
    try {
      setExpandedSession(await getSessionSummary(sessionId));
    } catch (cause) {
      setDetailsError(cause instanceof Error ? cause.message : "对话详情加载失败");
    } finally {
      setDetailsLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  const answeredHistory = history.filter((item) => {
    const count = Number(item.turn_count ?? item.summary?.turn_count ?? item.turns?.length ?? 0);
    return count > 0;
  });
  const completed = answeredHistory.filter((item) => item.status === "completed" || item.status === "finished");
  const scored = answeredHistory.map((item) => Number(item.summary?.average_score ?? item.average_score)).filter((value) => Number.isFinite(value));
  const average = scored.length ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : 0;
  const rows = answeredHistory.slice(0, 7);
  return (
    <div className="reports-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">训练报告</span>
          <h2>看见每一次回答，如何变得更好。</h2>
          <p>评分不是结论，原句证据和下一步行动才是。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()}>
          <RotateCcw size={16} />
          刷新数据
        </button>
      </section>
      {error ? (
        <div className="source-note" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>报告提示</strong>
            <p>
              {error}{" "}
              <button className="text-button" type="button" onClick={() => void load()}>
                重试
              </button>
            </p>
          </div>
        </div>
      ) : null}
      {loading ? (
        <div className="empty-list">
          <Gauge size={22} className="spin" />
          <p>正在加载训练历史和报告...</p>
        </div>
      ) : (
        <>
          <section className="report-stat-grid">
            <ReportStat label="训练会话" value={String(answeredHistory.length)} unit="次" trend={`已完成 ${completed.length} 次`} color="blue" />
            <ReportStat label="平均得分" value={average ? String(average) : "—"} unit="分" trend={scored.length ? "来自已评分会话" : "完成训练后生成"} color="mint" />
            <ReportStat label="持久化报告" value={String(reports.length)} unit="份" trend="数据库已保存" color="purple" />
            <ReportStat label="待复盘" value={String(Math.max(0, answeredHistory.length - completed.length))} unit="次" trend="继续完成训练" color="coral" />
          </section>
          <section className="report-table-panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">训练记录</span>
                <h3>最近完成的会话</h3>
              </div>
              <span className="small-tag green-tag">数据库</span>
            </div>
            {rows.length ? (
              <div className="report-table">
                <div className="report-table-head">
                  <span>岗位 / 场景</span>
                  <span>更新时间</span>
                  <span>得分</span>
                  <span>状态</span>
                </div>
                {rows.map((item, index) => {
                  const score = Number(item.summary?.average_score ?? item.average_score);
                  return (
                    <Fragment key={item.session_id || index}>
                      <button
                        className={`report-table-row report-row-button${expandedSessionId === item.session_id ? " expanded" : ""}`}
                        type="button"
                        onClick={() => item.session_id && void toggleDetails(item.session_id)}
                        disabled={!item.session_id}
                        aria-expanded={expandedSessionId === item.session_id}
                      >
                        <span>
                          <i className="table-dot dot-blue" />
                          <strong>
                            {item.role || "未命名岗位"} · {getModeLabel(item.mode || "technical")}
                          </strong>
                        </span>
                        <span>{formatDate(item.updated_at || item.created_at)}</span>
                        <span className="table-score">{Number.isFinite(score) ? Math.round(score) : "—"}</span>
                        <span className="report-row-status">
                          {item.status || "进行中"}
                          {item.session_id ? <ChevronDown size={13} /> : null}
                        </span>
                      </button>
                      {expandedSessionId === item.session_id ? <ReportConversationDetails session={expandedSession} loading={detailsLoading} error={detailsError} /> : null}
                    </Fragment>
                  );
                })}
              </div>
            ) : (
              <div className="empty-list">
                <CircleHelp size={22} />
                <p>暂无训练记录，开始一次训练后这里会自动生成。</p>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function ReportConversationDetails({ session, loading, error }: { session: SessionSummary | null; loading: boolean; error: string }) {
  if (loading) {
    return (
      <div className="report-detail-row report-detail-loading">
        <RotateCcw size={16} className="spin" />
        <span>正在加载对话详情...</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="report-detail-row report-detail-error" role="alert">
        <AlertCircle size={16} />
        <span>{error}</span>
      </div>
    );
  }
  const turns = session?.turns || [];
  if (!turns.length) {
    return <div className="report-detail-row report-detail-empty">该训练没有可展示的回答。</div>;
  }
  const sessionRole = session?.session?.role || session?.role || "未命名岗位";
  return (
    <div className="report-detail-row">
      <div className="report-detail-heading">
        <div>
          <span className="eyebrow">对话详情</span>
          <strong>{sessionRole}</strong>
        </div>
        <span>{turns.length} 轮回答</span>
      </div>
      <div className="conversation-list">
        {turns.map((rawTurn, index) => {
          const turn = rawTurn as {
            question_id?: string;
            question_text?: string;
            answer_text?: string;
            code?: string;
            created_at?: string;
            feedback?: BackendFeedback | null;
            algorithm_result?: AlgorithmResult | null;
          };
          const feedback = turn.feedback;
          const scores = feedback?.scores ? Object.entries(feedback.scores) : [];
          return (
            <article className="conversation-turn" key={`${turn.question_id || "question"}-${index}`}>
              <div className="conversation-turn-meta">
                <span>第 {index + 1} 轮</span>
                <span>{formatDate(turn.created_at)}</span>
              </div>
              <div className="conversation-block">
                <span className="conversation-label">面试官问题</span>
                <p>{turn.question_text || `问题 ${turn.question_id || index + 1}`}</p>
              </div>
              <div className="conversation-block answer-block">
                <span className="conversation-label">你的回答</span>
                {turn.answer_text ? <p>{turn.answer_text}</p> : null}
                {turn.code ? <pre>{turn.code}</pre> : null}
                {turn.algorithm_result ? (
                  <small>
                    判题结果：{turn.algorithm_result.passed}/{turn.algorithm_result.total} 个测试通过
                  </small>
                ) : null}
              </div>
              {feedback ? (
                <div className="conversation-feedback">
                  <div className="conversation-label">AI 反馈</div>
                  {scores.length ? (
                    <div className="conversation-score-list">
                      {scores.map(([label, value]) => (
                        <span key={label}>
                          {label} <strong>{value}</strong>
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {feedback.evidence_quotes?.length ? (
                    <p>
                      <strong>原句证据：</strong>
                      {feedback.evidence_quotes.join("；")}
                    </p>
                  ) : null}
                  {feedback.improvements?.length ? (
                    <p>
                      <strong>改进建议：</strong>
                      {feedback.improvements.join("；")}
                    </p>
                  ) : null}
                  {feedback.better_answer ? (
                    <p>
                      <strong>参考组织：</strong>
                      {feedback.better_answer}
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="conversation-feedback muted-feedback">该轮反馈尚未生成。</div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function formatDate(value: unknown) {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function ReportStat({ label, value, unit, trend, color }: { label: string; value: string; unit: string; trend: string; color: string }) {
  return (
    <article className="report-stat">
      <span className={`stat-icon stat-${color}`}>
        <Gauge size={17} />
      </span>
      <span className="stat-label">{label}</span>
      <div className="stat-value">
        <strong>{value}</strong>
        <span>{unit}</span>
      </div>
      <small>{trend}</small>
    </article>
  );
}

function SettingsPage() {
  const [localEnabled, setLocalEnabled] = useState(true);
  const [showEvidence, setShowEvidence] = useState(true);
  return (
    <div className="settings-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">系统设置</span>
          <h2>控制训练方式和模型使用。</h2>
          <p>默认优先使用本地模型，复杂反馈再路由到强模型。</p>
        </div>
      </section>
      <div className="settings-grid">
        <section className="settings-panel">
          <div className="panel-title-row">
            <div>
              <span className="eyebrow">模型路由</span>
              <h3>当前调用策略</h3>
            </div>
            <span className="small-tag green-tag">已生效</span>
          </div>
          <div className="route-list">
            <RouteRow icon={<CpuIcon />} title="本地双卡 4090" detail="抽取、embedding、基础评分" status="在线" active={localEnabled} onClick={() => setLocalEnabled((value) => !value)} />
            <RouteRow icon={<Sparkles size={17} />} title="第三方强模型" detail="复杂出题、压力面追问和长反馈" status="按需" active={true} />
            <RouteRow icon={<Database size={17} />} title="GraphRAG 检索" detail="岗位、技能、题目和来源的混合检索" status="在线" active={true} />
          </div>
        </section>
        <section className="settings-panel">
          <div className="panel-title-row">
            <div>
              <span className="eyebrow">训练偏好</span>
              <h3>让反馈更贴近你</h3>
            </div>
          </div>
          <div className="preference-row">
            <div>
              <strong>展示原句证据</strong>
              <p>反馈中保留回答里的关键句，方便复盘。</p>
            </div>
            <button className={showEvidence ? "toggle active" : "toggle"} type="button" aria-label="切换原句证据" onClick={() => setShowEvidence((value) => !value)}>
              <span />
            </button>
          </div>
          <div className="preference-row">
            <div>
              <strong>默认开启限时模式</strong>
              <p>压力面默认 30 秒，其他场景不计时。</p>
            </div>
            <button className="toggle" type="button" aria-label="切换限时模式">
              <span />
            </button>
          </div>
          <div className="privacy-note">
            <ShieldCheck size={16} />
            <span>你的回答默认不进入普通日志，可随时清理会话。</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function AccountPage({ auth, onAuthChange }: { auth: AuthState; onAuthChange: (value: AuthState) => void }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [displayName, setDisplayName] = useState(auth.user.display_name === "临时用户" ? "" : auth.user.display_name);
  const [email, setEmail] = useState(auth.user.email || "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      const next =
        mode === "register"
          ? await registerAccount({
              display_name: displayName.trim(),
              email: email.trim(),
              password,
            })
          : await loginAccount({ email: email.trim(), password });
      onAuthChange(next);
      navigate("/");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "认证服务暂不可用";
      setNotice(message === "email_already_registered" ? "该邮箱已经注册，请直接登录。" : message === "email_or_password_invalid" ? "邮箱或密码不正确。" : message === "email_invalid" ? "请输入有效的邮箱地址。" : message);
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setBusy(true);
    setNotice("");
    try {
      await logoutAccount();
      const guest = await createTemporaryUser();
      onAuthChange(guest);
      navigate("/");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "退出失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="account-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">用户中心</span>
          <h2>{auth.authenticated ? "管理你的独立账户。" : "保存并隔离你的求职工作区。"}</h2>
          <p>个人背景、JD、收藏、训练会话、回答、准备度和报告都只属于当前账户。</p>
        </div>
      </section>
      <section className="account-panel">
        {auth.authenticated ? (
          <div className="account-summary">
            <span className="account-avatar">
              <UserRound size={28} />
            </span>
            <div>
              <span className="small-tag green-tag">正式账户</span>
              <h3>{auth.user.display_name}</h3>
              <p>{auth.user.email}</p>
              <small>账户数据已由服务端身份校验隔离，客户端不能通过修改用户 ID 访问其他账户。</small>
            </div>
            <button className="secondary-button danger-button" type="button" disabled={busy} onClick={() => void logout()}>
              <LogOut size={16} />
              退出登录
            </button>
          </div>
        ) : (
          <>
            <div className="account-guest-note">
              <ShieldCheck size={18} />
              <div>
                <strong>当前是临时工作区</strong>
                <p>注册会直接升级当前临时用户，已经保存的档案、JD 和训练记录都会保留。</p>
              </div>
            </div>
            <div className="auth-tabs">
              <button className={mode === "register" ? "active" : ""} type="button" onClick={() => setMode("register")}>
                注册账户
              </button>
              <button className={mode === "login" ? "active" : ""} type="button" onClick={() => setMode("login")}>
                已有账户登录
              </button>
            </div>
            <form className="auth-form" onSubmit={(event) => void submit(event)}>
              {mode === "register" ? (
                <label>
                  <span>显示名称</span>
                  <div className="auth-input">
                    <UserRound size={17} />
                    <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} minLength={1} maxLength={80} required placeholder="例如：张三" />
                  </div>
                </label>
              ) : null}
              <label>
                <span>邮箱</span>
                <div className="auth-input">
                  <Mail size={17} />
                  <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required placeholder="name@example.com" />
                </div>
              </label>
              <label>
                <span>密码</span>
                <div className="auth-input">
                  <LockKeyhole size={17} />
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete={mode === "register" ? "new-password" : "current-password"}
                    minLength={mode === "register" ? 8 : 1}
                    maxLength={128}
                    required
                    placeholder={mode === "register" ? "至少 8 位" : "输入密码"}
                  />
                </div>
              </label>
              {notice ? (
                <div className="auth-error" role="alert">
                  <AlertCircle size={16} />
                  {notice}
                </div>
              ) : null}
              <button className="primary-button full-button" type="submit" disabled={busy}>
                {busy ? <Gauge className="spin" size={16} /> : <LogIn size={16} />}
                {mode === "register" ? "注册并保留当前数据" : "登录独立工作区"}
              </button>
            </form>
          </>
        )}
        {notice && auth.authenticated ? (
          <div className="auth-error" role="alert">
            <AlertCircle size={16} />
            {notice}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function RouteRow({ icon, title, detail, status, active, onClick }: { icon: ReactNode; title: string; detail: string; status: string; active: boolean; onClick?: () => void }) {
  return (
    <div className="route-row">
      <span className="route-icon">{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <span className="route-status">{status}</span>
      {onClick ? (
        <button className={active ? "toggle active" : "toggle"} type="button" aria-label={`切换 ${title}`} onClick={onClick}>
          <span />
        </button>
      ) : (
        <CheckCircle2 size={16} className="success-icon" />
      )}
    </div>
  );
}

function getPageTitle(pathname: string) {
  if (pathname === "/") return "总览";
  if (pathname.startsWith("/practice")) return "开始训练";
  if (pathname.startsWith("/match")) return "岗位匹配";
  if (pathname.startsWith("/materials")) return "求职资料";
  if (pathname.startsWith("/questions")) return "题库";
  if (pathname.startsWith("/reports")) return "训练报告";
  if (pathname.startsWith("/account")) return "用户中心";
  return "系统设置";
}

export default App;
