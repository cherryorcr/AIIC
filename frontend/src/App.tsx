import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  healthCheck,
  getSessionSummary,
  listFavorites,
  listJobs,
  listKnowledgeItems,
  listReports,
  listSessionHistory,
  loadFavorites,
  loadUserProfile,
  matchSession,
  queueQuestion,
  runAlgorithm,
  saveUserProfile,
  startSession,
  submitTurn,
  toggleFavorite,
} from "./api";
import type {
  AlgorithmResult,
  BackendQuestion,
  Feedback as BackendFeedback,
  MatchResponse,
  SessionSummary,
  StartSessionResponse,
  UserProfile,
} from "./api";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  Bell,
  BookOpen,
  BrainCircuit,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Code2,
  Database,
  FileQuestion,
  Gauge,
  GitBranch,
  LayoutDashboard,
  LibraryBig,
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
  X,
} from "lucide-react";

type ModeId = "technical" | "algorithm" | "behavioral" | "stress" | "case" | "research" | "hr";

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
  followUp: string;
  rubric: string[];
  tests?: Array<{
    args?: unknown[];
    kwargs?: Record<string, unknown>;
    expected?: unknown;
  }>;
  backend?: BackendQuestion;
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
  { label: "题库", path: "/questions", Icon: FileQuestion },
  { label: "训练报告", path: "/reports", Icon: BarChart3 },
];

const recentSessions = [
  {
    title: "后端开发工程师 · 技术面",
    mode: "技术面",
    score: 82,
    date: "今天 09:40",
    accent: "blue",
  },
  {
    title: "算法工程师 · 算法面",
    mode: "算法面",
    score: 74,
    date: "昨天 20:15",
    accent: "purple",
  },
  {
    title: "数据分析师 · 案例面",
    mode: "案例面",
    score: 88,
    date: "08 月 28 日",
    accent: "amber",
  },
];

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}

function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const title = getPageTitle(location.pathname);

  return (
    <div className={collapsed ? "app-shell app-shell-collapsed" : "app-shell"}>
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onToggle={() => setCollapsed((value) => !value)}
      />
      <div className="app-main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            type="button"
            aria-label="打开导航"
            onClick={() => setMobileOpen(true)}
          >
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
            <div className="profile-menu">
              <span className="avatar">L</span>
              <span className="profile-name">Lin</span>
              <ChevronDown size={15} />
            </div>
          </div>
        </header>
        <main className="page-container">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/practice" element={<PracticePage />} />
            <Route path="/match" element={<MatchPage />} />
            <Route path="/questions" element={<QuestionBankPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<DashboardPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Sidebar({
  collapsed,
  mobileOpen,
  onClose,
  onToggle,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
}) {
  const navigate = useNavigate();
  return (
    <>
      {mobileOpen ? (
        <button
          className="sidebar-backdrop"
          aria-label="关闭导航"
          type="button"
          onClick={onClose}
        />
      ) : null}
      <aside
        className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "sidebar-mobile-open" : ""}`}
      >
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
          <button
            className="icon-button sidebar-close"
            type="button"
            aria-label="关闭导航"
            onClick={onClose}
          >
            <X size={17} />
          </button>
          <button
            className="icon-button sidebar-collapse"
            type="button"
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
            onClick={onToggle}
          >
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
            <NavLink
              key={path}
              className={({ isActive }) => (isActive ? "side-link active" : "side-link")}
              end={end}
              to={path}
              onClick={onClose}
            >
              <Icon size={18} />
              <span>{label}</span>
              {label === "岗位匹配" ? <em>3</em> : null}
            </NavLink>
          ))}
          <span className="nav-label nav-label-spaced">管理</span>
          <NavLink
            className={({ isActive }) => (isActive ? "side-link active" : "side-link")}
            to="/settings"
            onClick={onClose}
          >
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
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="5" y="5" width="14" height="14" rx="2" />
      <path d="M9 9h6v6H9zM9 1v4M15 1v4M9 19v4M15 19v4M19 9h4M19 14h4M1 9h4M1 14h4" />
    </svg>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
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
              <h3>后端开发工程师</h3>
            </div>
            <button className="text-button" type="button" onClick={() => navigate("/match")}>
              查看匹配 <ArrowRight size={15} />
            </button>
          </div>
          <div className="readiness-body">
            <div className="score-ring">
              <span>78</span>
              <small>/100</small>
            </div>
            <div className="readiness-copy">
              <strong>基础扎实，补齐表达证据</strong>
              <p>系统设计和项目深度是当前最值得投入的两项能力。</p>
              <div className="progress-line">
                <span style={{ width: "78%" }} />
              </div>
              <div className="progress-meta">
                <span>较上周 +8</span>
                <span>目标 85</span>
              </div>
            </div>
          </div>
          <div className="skill-strip">
            <span>
              <i className="mini-dot mint" />
              已掌握 <b>8</b>
            </span>
            <span>
              <i className="mini-dot coral" />
              待加强 <b>3</b>
            </span>
            <span>
              <i className="mini-dot blue" />
              已完成训练 <b>12</b>
            </span>
          </div>
        </article>
        <article className="next-session-card">
          <div className="card-header">
            <div>
              <span className="eyebrow">继续上次训练</span>
              <h3>系统设计 · 缓存一致性</h3>
            </div>
            <span className="small-tag blue-tag">技术面</span>
          </div>
          <div className="session-detail">
            <div className="session-icon">
              <Database size={22} />
            </div>
            <div>
              <strong>第 4 / 6 题</strong>
              <span>预计还需 12 分钟 · 难度中高</span>
            </div>
          </div>
          <button
            className="secondary-button full-button"
            type="button"
            onClick={() => navigate("/practice")}
          >
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
            {recentSessions.map((session) => (
              <SessionRow key={session.title} session={session} />
            ))}
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
            <RecommendationItem
              icon={<GitBranch size={18} />}
              title="系统设计"
              detail="把方案讲成约束、取舍和结果"
              progress={62}
              color="blue"
            />
            <RecommendationItem
              icon={<MessageSquareText size={18} />}
              title="项目表达"
              detail="用数字证明你的个人贡献"
              progress={48}
              color="mint"
            />
            <RecommendationItem
              icon={<TimerReset size={18} />}
              title="压力追问"
              detail="30 秒内先给结论，再补证据"
              progress={35}
              color="coral"
            />
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

function RecommendationItem({
  icon,
  title,
  detail,
  progress,
  color,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  progress: number;
  color: string;
}) {
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

function SessionRow({ session }: { session: (typeof recentSessions)[number] }) {
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
        <strong>{session.score}</strong>
        <span>分</span>
      </div>
      <ArrowRight size={16} className="muted-icon" />
    </div>
  );
}

function backendQuestionToQuestion(
  item: BackendQuestion,
  mode: ModeId,
  fallback?: Question,
): Question {
  const prompt = item.question || fallback?.prompt || "请介绍一个与目标岗位相关的项目。";
  return {
    id: item.question_id,
    mode,
    title: fallback?.title || prompt.slice(0, 28),
    prompt,
    skills: item.skills?.length ? item.skills : fallback?.skills || [],
    difficulty: item.difficulty || fallback?.difficulty || "中",
    source: item.source_refs?.length
      ? item.source_refs.join(" · ")
      : fallback?.source || "synthetic_mock",
    followUp: item.follow_ups?.join(" ") || fallback?.followUp || "请补充一个具体事实或结果。",
    rubric: item.rubric?.length ? item.rubric : fallback?.rubric || [],
    tests: item.tests || fallback?.tests,
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
  };
  return (
    map[value || ""] ||
    (modeMeta.some((item) => item.id === value) ? (value as ModeId) : "technical")
  );
}

function questionFromKnowledge(item: BackendQuestion): Question {
  const mode = modeFromProcessType(item.process_type);
  const fallback =
    questions.find((candidate) => candidate.id === (item.id || item.question_id)) ||
    questions.find((candidate) => candidate.mode === mode);
  return backendQuestionToQuestion(
    {
      ...item,
      question_id: item.question_id || item.id || `Q-${Date.now()}`,
      source_refs:
        item.source_refs ||
        (item.source
          ? [String(item.source.title || item.source.url || item.source.type || "数据库题库")]
          : []),
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
  const fallback =
    questions.find((item) => item.id === start.question_id && item.mode === mode) ||
    questions.find((item) => item.mode === mode);
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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [feedback, setFeedback] = useState<BackendFeedback | null>(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<AlgorithmResult | null>(null);
  const [code, setCode] = useState(
    "def solution(s):\n    window = set()\n    left = 0\n    best = 0\n\n    for right, char in enumerate(s):\n        while char in window:\n            window.remove(s[left])\n            left += 1\n        window.add(char)\n        best = max(best, right - left + 1)\n\n    return best",
  );
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [modelOnline, setModelOnline] = useState(true);
  const mode = modeMeta.find((item) => item.id === activeMode) ?? modeMeta[0];
  const { Icon } = mode;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setSubmitted(false);
    setFeedback(null);
    setNextQuestionData(null);
    setAnswer("");
    setRunResult(null);
    const fallback = questions.find((item) => item.mode === activeMode) || questions[0];
    setQuestion(fallback);
    const savedProfile = loadUserProfile();
    const requestedSession = searchParams.get("session");
    const sessionRequest = requestedSession
      ? getSessionSummary(requestedSession)
      : startSession({
          mode: activeMode,
          role: "后端开发工程师",
          job_text: savedProfile.job_text || "Python FastAPI PostgreSQL Redis Docker 系统设计",
          user_profile: {
            skills: savedProfile.skills.length
              ? savedProfile.skills
              : ["Python", "FastAPI", "PostgreSQL"],
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
        const sessionMode = requestedSession
          ? (persisted.mode as ModeId) || activeMode
          : activeMode;
        if (requestedSession && sessionMode !== activeMode) {
          setActiveMode(sessionMode as ModeId);
        }
        const current = (persisted as SessionSummary).current_question as
          BackendQuestion | null | undefined;
        setQuestion(
          current
            ? backendQuestionToQuestion(current, sessionMode as ModeId, fallback)
            : questionFromStart(data as StartSessionResponse, sessionMode as ModeId),
        );
        setQuestionIndex(0);
      } else {
        setSessionId(null);
        setError("后端暂不可用，当前显示演示题；启动 FastAPI 后会自动联调。");
      }
      if (healthResult.status === "fulfilled")
        setModelOnline(Boolean(healthResult.value.status === "ok"));
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
  function nextQuestion() {
    const fallback = questions.find((item) => item.mode === activeMode) || questions[0];
    setQuestion(nextQuestionData || fallback);
    setNextQuestionData(null);
    setQuestionIndex((index) => index + 1);
    setSubmitted(false);
    setFeedback(null);
    setRunResult(null);
    setAnswer("");
  }
  async function submitAnswer() {
    if (answer.trim().length < 8 || !sessionId || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const result = await submitTurn(sessionId, {
        question_id: question.id,
        answer_text: answer,
      });
      setFeedback(result.feedback);
      setSubmitted(true);
      setNextQuestionData(
        result.next_question
          ? backendQuestionToQuestion(result.next_question, activeMode, question)
          : null,
      );
    } catch {
      setError("提交失败，回答已保留在当前页面，请检查后端服务后重试。");
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
      <section className="mode-switcher">
        {modeMeta.map((item) => {
          const ItemIcon = item.Icon;
          return (
            <button
              key={item.id}
              type="button"
              className={activeMode === item.id ? `mode-tab active tab-${item.color}` : "mode-tab"}
              onClick={() => changeMode(item.id)}
            >
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
          <span>
            建议用时{" "}
            {activeMode === "stress" ? "30 秒" : activeMode === "algorithm" ? "20 分钟" : "5 分钟"}
          </span>
        </div>
        <div className="progress-meta">
          <span>训练进度</span>
          <div className="practice-progress">
            <span style={{ width: `${Math.min(22 + questionIndex * 12, 92)}%` }} />
          </div>
          <strong>{Math.min(22 + questionIndex * 12, 92)}%</strong>
        </div>
      </section>
      <div
        className={activeMode === "algorithm" ? "practice-grid algorithm-grid" : "practice-grid"}
      >
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
            <button className="text-button" type="button">
              查看来源
            </button>
          </div>
          {activeMode !== "algorithm" ? (
            <>
              <label className="answer-label" htmlFor="answer">
                你的回答 <span>{answer.length} 字</span>
              </label>
              <textarea
                id="answer"
                className="answer-input"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder={
                  activeMode === "stress"
                    ? "先说结论，再给一个事实。注意控制在 30 秒内..."
                    : "把你的思路写下来，系统会按当前场景的评分标准给出反馈..."
                }
              />
              <div className="answer-actions">
                <span>
                  <CircleHelp size={15} />
                  不确定时可以先写要点，提交后再看追问。
                </span>
                <button
                  className="primary-button"
                  type="button"
                  disabled={answer.trim().length < 8 || !sessionId || submitting}
                  onClick={submitAnswer}
                >
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
              <button className="secondary-button" type="button" onClick={nextQuestion}>
                换一道题 <ArrowRight size={15} />
              </button>
            </div>
          ) : null}
        </div>
        {activeMode === "algorithm" ? (
          <CodeEditor
            code={code}
            setCode={setCode}
            running={running}
            runResult={runResult}
            onRun={runCode}
          />
        ) : (
          <FeedbackPanel
            submitted={submitted}
            feedback={feedback}
            question={question}
            onRetry={() => {
              setSubmitted(false);
              setFeedback(null);
              setAnswer("");
            }}
            onNext={nextQuestion}
          />
        )}
      </div>
    </div>
  );
}

function CodeEditor({
  code,
  setCode,
  running,
  runResult,
  onRun,
}: {
  code: string;
  setCode: (value: string) => void;
  running: boolean;
  runResult: AlgorithmResult | null;
  onRun: () => void;
}) {
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
        <textarea
          aria-label="算法题代码"
          spellCheck={false}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
      </div>
      <div className="test-status">
        {status === "passed" ? (
          <>
            <CheckCircle2 size={16} className="success-icon" />
            <span>
              {runResult?.passed} / {runResult?.total} 测试用例通过 ·{" "}
              {Math.round(runResult?.runtime_ms || 0)}ms
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
      <button
        className="primary-button full-button"
        type="button"
        onClick={onRun}
        disabled={running}
      >
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
};

function FeedbackPanel({
  submitted,
  feedback,
  question,
  onRetry,
  onNext,
}: {
  submitted: boolean;
  feedback: BackendFeedback | null;
  question: Question;
  onRetry: () => void;
  onNext: () => void;
}) {
  const scoreEntries = feedback ? Object.entries(feedback.scores) : [];
  const average = scoreEntries.length
    ? Math.round(
        (scoreEntries.reduce((sum, [, value]) => sum + Number(value), 0) / scoreEntries.length) *
          20,
      )
    : 0;
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
              <ScoreBar
                key={key}
                label={scoreLabel[key] || key}
                score={Math.round(Number(value) * 20)}
                color={["blue", "mint", "purple", "coral"][index % 4]}
              />
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
          <div className="feedback-actions">
            <button className="secondary-button" type="button" onClick={onRetry}>
              重新回答
            </button>
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

function MatchPage() {
  const navigate = useNavigate();
  const [selectedRole, setSelectedRole] = useState("后端开发工程师");
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
  const [draftSkills, setDraftSkills] = useState(() => profile.skills.join(", "));
  const [draftProjects, setDraftProjects] = useState(() => profile.projects.join(", "));
  const [draftJob, setDraftJob] = useState(
    () => profile.job_text || "Python FastAPI PostgreSQL Redis Docker 系统设计",
  );
  const [match, setMatch] = useState<MatchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fallbackRoles = [
    {
      name: "后端开发工程师",
      company: "互联网 / SaaS",
      fallbackSkills: ["Python", "FastAPI", "PostgreSQL", "系统设计"],
      gap: ["分布式一致性", "故障排查"],
    },
    {
      name: "算法工程师",
      company: "AI 基础设施",
      fallbackSkills: ["Python", "算法", "机器学习"],
      gap: ["模型部署", "实验设计"],
    },
    {
      name: "数据分析师",
      company: "消费 / 业务分析",
      fallbackSkills: ["SQL", "指标设计", "Python"],
      gap: ["因果推断", "业务沟通"],
    },
  ];
  const roles = jobs.length
    ? jobs.map((job) => ({
        id: job.id || job.job_id,
        name: job.title || job.name || job.role || "未命名岗位",
        company: job.company || "已保存岗位",
        fallbackSkills: job.skills?.length ? job.skills : ["岗位技能"],
        gap: ["待补强技能"],
        jd_text: job.jd_text || job.job_text || "",
      }))
    : fallbackRoles;
  const role = roles.find((item) => item.name === selectedRole) ?? roles[0];
  const matchedSkills = match?.matched_skills?.length
    ? match.matched_skills
    : profile.skills.length
      ? profile.skills
      : role.fallbackSkills;
  const score = Math.min(98, Math.max(45, 58 + matchedSkills.length * 8));

  async function refreshMatch() {
    setLoading(true);
    setError("");
    try {
      const session = await startSession({
        mode: "technical",
        role: selectedRole,
        job_text: draftJob,
        user_profile: { skills: profile.skills, projects: profile.projects },
        difficulty: "medium",
      });
      const result = await matchSession(session.session_id, {
        difficulty: "medium",
      });
      setMatch(result);
    } catch (cause) {
      setMatch(null);
      setError(cause instanceof Error ? cause.message : "岗位匹配服务暂不可用，已显示本地建议。");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let cancelled = false;
    void listJobs()
      .then((result) => {
        if (cancelled || !result.length) return;
        setJobs(result);
        const first = result[0];
        const firstName = first.title || first.name || first.role || "未命名岗位";
        setSelectedRole((current) =>
          result.some((job) => (job.title || job.name || job.role) === current)
            ? current
            : firstName,
        );
        if (first.jd_text || first.job_text) setDraftJob(String(first.jd_text || first.job_text));
      })
      .catch(() => {
        /* local fallback roles remain usable */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (role) void refreshMatch();
  }, [selectedRole, jobs.length]);
  async function saveProfile() {
    setSaving(true);
    setError("");
    const next: UserProfile = {
      ...profile,
      skills: draftSkills
        .split(/[,，\n]/)
        .map((x) => x.trim())
        .filter(Boolean),
      projects: draftProjects
        .split(/[,，\n]/)
        .map((x) => x.trim())
        .filter(Boolean),
      job_text: draftJob,
    };
    await saveUserProfile(next);
    setProfile(next);
    setSaving(false);
    await refreshMatch();
  }
  return (
    <div className="match-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">岗位匹配</span>
          <h2>把个人经历，映射到真实岗位。</h2>
          <p>GraphRAG 会结合 JD、技能图谱和你的训练证据，给出可解释的匹配结果。</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() =>
            document.getElementById("profile-editor")?.scrollIntoView({ behavior: "smooth" })
          }
        >
          <Plus size={16} />
          编辑个人资料
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
            {roles.map((item) => (
              <button
                key={item.name}
                type="button"
                className={
                  selectedRole === item.name ? "role-list-item selected" : "role-list-item"
                }
                onClick={() => {
                  setSelectedRole(item.name);
                  if ("jd_text" in item && item.jd_text) setDraftJob(String(item.jd_text));
                }}
              >
                <span
                  className={`role-score score-${item.name === "后端开发工程师" ? "high" : item.name === "算法工程师" ? "mid" : "low"}`}
                >
                  {item.name === selectedRole
                    ? score
                    : item.name === "后端开发工程师"
                      ? 88
                      : item.name === "算法工程师"
                        ? 79
                        : 71}
                </span>
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.company}</small>
                </span>
                <ArrowRight size={15} />
              </button>
            ))}
          </div>
          <button
            className="role-add-button"
            type="button"
            onClick={() => setDraftJob(`${draftJob}\n\n请粘贴新的 JD 内容`)}
          >
            <Plus size={15} />
            导入新的 JD
          </button>
        </aside>
        <div className="match-detail">
          <div className="match-detail-top">
            <div>
              <span className="eyebrow">当前匹配结果</span>
              <h3>{role.name}</h3>
              <p>
                {role.company} · {loading ? "正在计算…" : "已同步数据库"}
              </p>
            </div>
            <button
              className="primary-button"
              type="button"
              onClick={() => navigate(`/practice?role=${encodeURIComponent(role.name)}`)}
            >
              <Sparkles size={16} />
              用此岗位开始训练
            </button>
          </div>
          <div className="match-score-grid">
            <div className="match-score-card">
              <span className="eyebrow">综合匹配度</span>
              <div className="large-score">
                <strong>{loading ? "—" : score}</strong>
                <span>/100</span>
              </div>
              <div className="score-caption">
                <span className="status-dot" />
                基于 {matchedSkills.length} 个技能节点计算
              </div>
            </div>
            <div className="match-explanation">
              <div className="explanation-icon">
                <GitBranch size={19} />
              </div>
              <div>
                <strong>为什么匹配</strong>
                <p>
                  {match?.questions?.length
                    ? `已从题库召回 ${match.questions.length} 道相关题目，覆盖 ${matchedSkills.slice(0, 4).join("、")}。`
                    : "你的个人技能和项目会用于召回岗位相关题目，并在训练中持续更新匹配结果。"}
                </p>
                <div className="source-line">
                  <ShieldCheck size={14} />
                  来源和匹配分数可在题库中追溯
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
                      <strong>{Math.max(68, 96 - index * 7)}%</strong>
                    </div>
                  ))}
                </div>
              </div>
              <div className="skill-column">
                <span className="column-label warning-label">
                  <AlertCircle size={15} />
                  建议补强
                </span>
                <div className="skill-chip-list">
                  {role.gap.map((skill) => (
                    <div className="skill-chip gap" key={skill}>
                      <span>{skill}</span>
                      <button
                        type="button"
                        onClick={() => navigate("/practice")}
                        aria-label={`训练 ${skill}`}
                      >
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="match-trace">
            <div className="trace-step done">
              <span>
                <Check size={14} />
              </span>
              <div>
                <strong>JD 解析</strong>
                <small>{draftJob.trim() ? "已保存岗位描述" : "等待 JD"}</small>
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
          <section id="profile-editor" className="settings-panel" style={{ marginTop: 20 }}>
            <div className="panel-title-row">
              <div>
                <span className="eyebrow">用户档案</span>
                <h3>保存技能、项目经历和 JD</h3>
              </div>
              <span className="small-tag green-tag">本地 + API</span>
            </div>
            <div className="preference-row">
              <div>
                <strong>技能</strong>
                <p>使用逗号或换行分隔</p>
              </div>
              <input
                className="search-input profile-field"
                value={draftSkills}
                onChange={(event) => setDraftSkills(event.target.value)}
              />
            </div>
            <div className="preference-row">
              <div>
                <strong>项目经历</strong>
                <p>项目名或一句话成果</p>
              </div>
              <input
                className="search-input profile-field"
                value={draftProjects}
                onChange={(event) => setDraftProjects(event.target.value)}
              />
            </div>
            <div className="preference-row">
              <div>
                <strong>目标 JD</strong>
                <p>匹配和面试题召回的输入</p>
              </div>
              <textarea
                className="answer-input profile-field"
                rows={3}
                value={draftJob}
                onChange={(event) => setDraftJob(event.target.value)}
              />
            </div>
            <button
              className="primary-button"
              type="button"
              onClick={() => void saveProfile()}
              disabled={saving}
            >
              {saving ? "保存中…" : "保存并重新匹配"} <ArrowRight size={15} />
            </button>
          </section>
        </div>
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
      setSelected((current) =>
        current && mapped.some((item) => item.id === current.id)
          ? current
          : mapped[0] || questions[0],
      );
    } catch (cause) {
      setItems(questions);
      setSelected((current) => current || questions[0]);
      setError(
        cause instanceof Error
          ? `${cause.message}，当前显示演示题库。`
          : "题库服务暂不可用，当前显示演示题库。",
      );
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
  const filtered = items.filter(
    (item) =>
      (mode === "all" || item.mode === mode) &&
      `${item.title}${item.prompt}${item.skills.join("")}${item.source}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
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
        user_profile: { skills: profile.skills, projects: profile.projects },
        difficulty:
          selected.difficulty === "高" || selected.difficulty === "hard"
            ? "hard"
            : selected.difficulty === "低"
              ? "easy"
              : "medium",
      });
      if (selected.backend) queueQuestion(selected.backend);
      navigate(
        `/practice?session=${encodeURIComponent(session.session_id)}&question=${encodeURIComponent(session.question_id)}`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? `${cause.message}，无法创建训练会话。`
          : "创建训练会话失败，请重试。",
      );
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
        <button
          className="secondary-button"
          type="button"
          onClick={() => setError("提交题目需要登录后开放，当前可先将题目加入训练。")}
        >
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
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索题目、技能或岗位..."
              />
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
              <button
                key={item.id}
                type="button"
                className={mode === item.id ? "filter-tab active" : "filter-tab"}
                onClick={() => setMode(item.id as "all" | ModeId)}
              >
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
                <button
                  key={item.id}
                  type="button"
                  className={
                    selected?.id === item.id ? "question-list-item selected" : "question-list-item"
                  }
                  onClick={() => setSelected(item)}
                >
                  <div className={`question-list-icon question-icon-${item.mode}`}>
                    <ModeIcon mode={item.mode} />
                  </div>
                  <div className="question-list-copy">
                    <div>
                      <strong>{item.title}</strong>
                      <span className="difficulty-tag">{item.difficulty}</span>
                      {favorites.includes(item.id) ? (
                        <span className="small-tag green-tag">已收藏</span>
                      ) : null}
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
              <span
                className={`mode-badge badge-${modeMeta.find((item) => item.id === selected.mode)?.color ?? "blue"}`}
              >
                <ModeIcon mode={selected.mode} />
                {getModeLabel(selected.mode)}
              </span>
              <button
                className={favorites.includes(selected.id) ? "icon-button active" : "icon-button"}
                type="button"
                aria-label="收藏题目"
                onClick={() => void favorite()}
              >
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
            </div>
            <button
              className="primary-button full-button"
              type="button"
              onClick={() => void addToTraining()}
              disabled={joining}
            >
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

function LegacyReportsPage() {
  return (
    <div className="reports-page">
      <section className="page-intro">
        <div>
          <span className="eyebrow">训练报告</span>
          <h2>看见每一次回答，如何变得更好。</h2>
          <p>评分不是结论，原句证据和下一步行动才是。</p>
        </div>
        <button className="secondary-button" type="button">
          <BarChart3 size={16} />
          导出本周报告
        </button>
      </section>
      <section className="report-stat-grid">
        <ReportStat label="本周训练" value="8" unit="次" trend="较上周 +3" color="blue" />
        <ReportStat label="平均得分" value="81" unit="分" trend="较上周 +6" color="mint" />
        <ReportStat label="连续训练" value="5" unit="天" trend="保持住" color="purple" />
        <ReportStat label="待补强技能" value="3" unit="项" trend="已完成 2 项" color="coral" />
      </section>
      <section className="report-grid">
        <div className="report-chart-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">能力趋势</span>
              <h3>最近 7 次训练</h3>
            </div>
            <button className="select-button" type="button">
              全部场景 <ChevronDown size={15} />
            </button>
          </div>
          <div className="chart-wrap">
            <div className="chart-y-axis">
              <span>100</span>
              <span>75</span>
              <span>50</span>
              <span>25</span>
              <span>0</span>
            </div>
            <div className="chart-area">
              <div className="chart-grid-lines">
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
              <div className="chart-bars">
                {[64, 72, 69, 78, 75, 84, 81].map((value, index) => (
                  <div className="chart-bar-column" key={index}>
                    <div className="chart-bar" style={{ height: `${value}%` }}>
                      <span>{value}</span>
                    </div>
                    <small>
                      {["08/24", "08/25", "08/26", "08/27", "08/28", "08/29", "今天"][index]}
                    </small>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="chart-legend">
            <span>
              <i className="legend-dot blue-dot" />
              综合得分
            </span>
            <span>
              <i className="legend-dot mint-dot" />
              目标线 85
            </span>
          </div>
        </div>
        <aside className="report-insight-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">AI 总结</span>
              <h3>本周的关键变化</h3>
            </div>
            <Sparkles size={17} className="blue-icon" />
          </div>
          <div className="insight-highlight">
            <strong>+18%</strong>
            <span>系统设计回答完整度</span>
          </div>
          <p>你已经能稳定说清架构模块，下一步是把“为什么这样选”说得更具体。</p>
          <div className="insight-list">
            <div>
              <CheckCircle2 size={15} />
              <span>能给出明确排查顺序</span>
            </div>
            <div>
              <CheckCircle2 size={15} />
              <span>项目结果开始出现数据证据</span>
            </div>
            <div>
              <AlertCircle size={15} />
              <span>压力追问时结论出现较晚</span>
            </div>
          </div>
          <button className="secondary-button full-button" type="button">
            查看完整复盘 <ArrowRight size={15} />
          </button>
        </aside>
      </section>
      <section className="report-table-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">训练记录</span>
            <h3>最近完成的会话</h3>
          </div>
          <button className="text-button" type="button">
            查看全部 <ArrowRight size={15} />
          </button>
        </div>
        <div className="report-table">
          <div className="report-table-head">
            <span>岗位 / 场景</span>
            <span>完成时间</span>
            <span>得分</span>
            <span>变化</span>
          </div>
          {recentSessions.map((session, index) => (
            <div className="report-table-row" key={session.title}>
              <span>
                <i className={`table-dot dot-${session.accent}`} />
                <strong>{session.title}</strong>
              </span>
              <span>{session.date}</span>
              <span className="table-score">{session.score}</span>
              <span className={index === 1 ? "down-change" : "up-change"}>
                {index === 1 ? "-2" : `+${index + 3}`}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ReportsPage() {
  const [history, setHistory] = useState<SessionSummary[]>([]);
  const [reports, setReports] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
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
  useEffect(() => {
    void load();
  }, []);
  const completed = history.filter(
    (item) => item.status === "completed" || item.status === "finished",
  );
  const scored = history
    .map((item) => Number(item.summary?.average_score ?? item.average_score))
    .filter((value) => Number.isFinite(value));
  const average = scored.length ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : 0;
  const rows = history.slice(0, 7);
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
            <ReportStat
              label="训练会话"
              value={String(history.length)}
              unit="次"
              trend={`已完成 ${completed.length} 次`}
              color="blue"
            />
            <ReportStat
              label="平均得分"
              value={average ? String(average) : "—"}
              unit="分"
              trend={scored.length ? "来自已评分会话" : "完成训练后生成"}
              color="mint"
            />
            <ReportStat
              label="持久化报告"
              value={String(reports.length)}
              unit="份"
              trend="数据库已保存"
              color="purple"
            />
            <ReportStat
              label="待复盘"
              value={String(Math.max(0, history.length - completed.length))}
              unit="次"
              trend="继续完成训练"
              color="coral"
            />
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
                    <div className="report-table-row" key={item.session_id || index}>
                      <span>
                        <i className="table-dot dot-blue" />
                        <strong>
                          {item.role || "未命名岗位"} · {getModeLabel(item.mode || "technical")}
                        </strong>
                      </span>
                      <span>{formatDate(item.updated_at || item.created_at)}</span>
                      <span className="table-score">
                        {Number.isFinite(score) ? Math.round(score) : "—"}
                      </span>
                      <span>{item.status || "进行中"}</span>
                    </div>
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

function ReportStat({
  label,
  value,
  unit,
  trend,
  color,
}: {
  label: string;
  value: string;
  unit: string;
  trend: string;
  color: string;
}) {
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
            <RouteRow
              icon={<CpuIcon />}
              title="本地双卡 4090"
              detail="抽取、embedding、基础评分"
              status="在线"
              active={localEnabled}
              onClick={() => setLocalEnabled((value) => !value)}
            />
            <RouteRow
              icon={<Sparkles size={17} />}
              title="第三方强模型"
              detail="复杂出题、压力面追问和长反馈"
              status="按需"
              active={true}
            />
            <RouteRow
              icon={<Database size={17} />}
              title="GraphRAG 检索"
              detail="岗位、技能、题目和来源的混合检索"
              status="在线"
              active={true}
            />
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
            <button
              className={showEvidence ? "toggle active" : "toggle"}
              type="button"
              aria-label="切换原句证据"
              onClick={() => setShowEvidence((value) => !value)}
            >
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

function RouteRow({
  icon,
  title,
  detail,
  status,
  active,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  status: string;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <div className="route-row">
      <span className="route-icon">{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <span className="route-status">{status}</span>
      {onClick ? (
        <button
          className={active ? "toggle active" : "toggle"}
          type="button"
          aria-label={`切换 ${title}`}
          onClick={onClick}
        >
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
  if (pathname.startsWith("/questions")) return "题库";
  if (pathname.startsWith("/reports")) return "训练报告";
  return "系统设置";
}

export default App;
