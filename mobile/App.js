import { useEffect, useRef, useState } from "react";
import { StatusBar } from "expo-status-bar";
import * as Device from "expo-device";
import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import {
  ActivityIndicator,
  Alert,
  AppState,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { loadBacklog, loadBoards, loadCalendarIssues, loadCatalog, loadCompletedAt, loadInboxIssues, loadIssueDetail, loadProfile, loadProjectSprints, loadSnapshots, login, read, renameLabel, revokeToken, send } from "./src/api";
import { backlogView } from "./src/backlog";
import { boardView } from "./src/board";
import { calendarView, focusForView, moveFocus } from "./src/calendar";
import { arrangeInbox, blankLayout, hideSection, homeKey, moveSection, parseLayout, showSection } from "./src/home";
import { inboxView } from "./src/inbox";
import { findView } from "./src/find";
import { blankFilter, filterMenus, labelOptions, peopleOptions, projectOptions, sprintOptions, toggleChoice } from "./src/filters";
import { BASES, DELETE_BODY, DELETE_TITLE, DELETED, FREQS, MONTHS, PRIORITIES, SCOPES, SPAWNS, WEEKDAYS, blankRecipe, prepareRecipe, recipeFromSeries, seriesView } from "./src/series";
import { completionNotice, NEEDS_CONNECTION, planningView, prepareSprint, prepareSprintUpdate, sprintDetail } from "./src/planning";
import { healthUrl, isConnected, parseOrigin } from "./src/origin";
import { ALWAYS, ON_LAUNCH, ON_RESUME, shouldUnlock } from "./src/lock";
import { applyPasswordEdit, maskPassword } from "./src/password";
import { NO_ACTIVE_SPRINT, NO_ISSUES, NO_PROJECTS } from "./src/work";
import {
  NOT_ON_SERVER,
  choosePhone,
  chooseServer,
  discardIssue,
  dropProject,
  emptyStore,
  enableProject,
  findIssue,
  hasWaiting,
  queueComment,
  queueCreate,
  queueDelete,
  queueRecreate,
  queueRemoveComment,
  queueUpdate,
  rememberDetail,
  storeKey,
  workView,
} from "./src/offline";
import { pullLibrary } from "./src/sync";
import { inputWhen, prepareCreate, prepareUpdate } from "./src/create";
import { formatMinutes, issueKeyParts, linkEnds, savedIssueId } from "./src/issue";

const ADDRESS_KEY = "keel.serverAddress";
const LOCK_KEY = "keel.lockSetting";
const TOKEN_KEY = "keel.token";
const TOKEN_ID_KEY = "keel.tokenId";
const NAME_KEY = "keel.displayName";
const LABEL_KEY = "keel.label";
const USER_ID_KEY = "keel.userId";
const CONNECTED = "Connected";
const FAILED = "Could not connect.";

const LOCK_OPTIONS = [
  { id: ALWAYS, title: "Remain unlocked" },
  { id: ON_RESUME, title: "Unlock after switching away" },
  { id: ON_LAUNCH, title: "Unlock after the app is closed" },
];

function deviceLabel() {
  const name = (Device.deviceName || Device.modelName || "Android").trim();
  return (name || "Android").slice(0, 100);
}

export default function App() {
  const [phase, setPhase] = useState("booting");
  const [address, setAddress] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState("idle");
  const [busy, setBusy] = useState(false);
  const [account, setAccount] = useState(null);
  const [lockSetting, setLockSetting] = useState(ON_LAUNCH);
  const [hasDeviceLock, setHasDeviceLock] = useState(false);
  const [draftLabel, setDraftLabel] = useState("");
  const [issueId, setIssueId] = useState(null);
  const [library, setLibrary] = useState(emptyStore());
  const [libraryReady, setLibraryReady] = useState(false);
  const [workError, setWorkError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const prompting = useRef(false);
  const listPhase = useRef("home");
  const [remoteIssues, setRemoteIssues] = useState(null);
  const [inboxMode, setInboxMode] = useState("loading");
  const [remoteBoards, setRemoteBoards] = useState(null);
  const [boardMode, setBoardMode] = useState("loading");
  const [boardProjectId, setBoardProjectId] = useState(null);
  const [remoteBacklog, setRemoteBacklog] = useState(null);
  const [remoteSprints, setRemoteSprints] = useState(null);
  const [backlogMode, setBacklogMode] = useState("loading");
  const [backlogProjectId, setBacklogProjectId] = useState(null);
  const [planningSprints, setPlanningSprints] = useState(null);
  const [planningMode, setPlanningMode] = useState("loading");
  const [planningProjectId, setPlanningProjectId] = useState(null);
  const [openSprint, setOpenSprint] = useState(null);
  const [sprintNotice, setSprintNotice] = useState("");
  const [findResult, setFindResult] = useState(null);
  const [remoteCalendar, setRemoteCalendar] = useState(null);
  const [completedAt, setCompletedAt] = useState(null);
  const [calendarLink, setCalendarLink] = useState("loading");
  const [calendarProjectId, setCalendarProjectId] = useState(null);
  const [calendarViewName, setCalendarViewName] = useState("month");
  const [calendarWhen, setCalendarWhen] = useState("start");
  const [calendarFocus, setCalendarFocus] = useState(localToday);
  const [remoteSeries, setRemoteSeries] = useState(null);
  const [scheduleLink, setScheduleLink] = useState("loading");
  const [scheduleProjectId, setScheduleProjectId] = useState(null);
  const [openSeries, setOpenSeries] = useState(null);
  const [recipe, setRecipe] = useState(blankRecipe);
  const [recipeMode, setRecipeMode] = useState("create");
  const [recipeScope, setRecipeScope] = useState("series");
  const [recipeIssue, setRecipeIssue] = useState(null);
  const [scheduleNotice, setScheduleNotice] = useState("");
  const [listFilter, setListFilter] = useState(blankFilter);
  const [filterSprints, setFilterSprints] = useState([]);
  const [homeLayout, setHomeLayout] = useState(null);
  const accountRef = useRef(null);
  const lockRef = useRef(ON_LAUNCH);
  const deviceLockRef = useRef(false);

  useEffect(() => {
    accountRef.current = account;
  }, [account]);

  useEffect(() => {
    lockRef.current = lockSetting;
  }, [lockSetting]);

  useEffect(() => {
    deviceLockRef.current = hasDeviceLock;
  }, [hasDeviceLock]);

  useEffect(() => {
    let active = true;
    boot()
      .then((next) => {
        if (active) {
          applyBoot(next);
        }
      })
      .catch(() => {
        if (active) {
          setMessage("Enter the server address.");
          setPhase("signedOut");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (next !== "active" || prompting.current) {
        return;
      }
      if (
        shouldUnlock({
          signedIn: accountRef.current !== null,
          setting: lockRef.current,
          hasDeviceLock: deviceLockRef.current,
          event: "resume",
        })
      ) {
        promptUnlock();
      }
    });
    return () => sub.remove();
  }, []);

  async function boot() {
    const [savedAddress, savedLock, token, tokenId, displayName, label, userId, level] =
      await Promise.all([
        AsyncStorage.getItem(ADDRESS_KEY),
        AsyncStorage.getItem(LOCK_KEY),
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(TOKEN_ID_KEY),
        SecureStore.getItemAsync(NAME_KEY),
        SecureStore.getItemAsync(LABEL_KEY),
        SecureStore.getItemAsync(USER_ID_KEY),
        LocalAuthentication.getEnrolledLevelAsync(),
      ]);
    const setting = savedLock || ON_LAUNCH;
    const enrolled = level !== LocalAuthentication.SecurityLevel.NONE;
    const parsed = savedAddress ? parseOrigin(savedAddress) : null;
    const signedIn =
      token && tokenId && displayName && label && parsed && parsed.ok
        ? {
            token,
            tokenId,
            displayName,
            label,
            origin: parsed.origin,
            userId: userId || null,
          }
        : null;
    return { savedAddress: savedAddress || "", setting, enrolled, signedIn };
  }

  function applyBoot(next) {
    setAddress(next.savedAddress);
    setLockSetting(next.setting);
    setHasDeviceLock(next.enrolled);
    setAccount(next.signedIn);
    if (!next.savedAddress) {
      setMessage("Enter the server address.");
    }
    if (
      shouldUnlock({
        signedIn: next.signedIn !== null,
        setting: next.setting,
        hasDeviceLock: next.enrolled,
        event: "launch",
      })
    ) {
      promptUnlock();
      return;
    }
    listPhase.current = "home";
    setPhase(next.signedIn ? "home" : "signedOut");
  }

  async function promptUnlock() {
    if (prompting.current) {
      return;
    }
    prompting.current = true;
    setPhase("locked");
    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock Keel",
        cancelLabel: "Cancel",
        disableDeviceFallback: false,
      });
      listPhase.current = "home";
      setPhase(result.success ? "home" : "locked");
    } catch {
      setPhase("locked");
    } finally {
      prompting.current = false;
    }
  }

  function onAddressChange(value) {
    setAddress(value);
    setTone("idle");
    setMessage(value.trim() ? "" : "Enter the server address.");
  }

  async function onCheck() {
    const parsed = parseOrigin(address);
    if (!parsed.ok) {
      setTone("error");
      setMessage(parsed.message);
      if (!address.trim()) {
        await AsyncStorage.removeItem(ADDRESS_KEY);
      }
      return;
    }
    await AsyncStorage.setItem(ADDRESS_KEY, parsed.origin);
    setAddress(parsed.origin);
    setBusy(true);
    setMessage("");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(healthUrl(parsed.origin), {
        signal: controller.signal,
      });
      let body = null;
      try {
        body = await response.json();
      } catch {
        body = null;
      }
      if (response.ok && isConnected(body)) {
        setTone("ok");
        setMessage(CONNECTED);
      } else {
        setTone("error");
        setMessage(FAILED);
      }
    } catch {
      setTone("error");
      setMessage(FAILED);
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  async function onSignIn() {
    const parsed = parseOrigin(address);
    if (!parsed.ok) {
      setTone("error");
      setMessage(parsed.message);
      return;
    }
    if (!username.trim() || !password) {
      setTone("error");
      setMessage("Enter your username and password.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const body = await login(
        parsed.origin,
        username.trim(),
        password,
        deviceLabel(),
      );
      await SecureStore.setItemAsync(TOKEN_KEY, body.token);
      await SecureStore.setItemAsync(TOKEN_ID_KEY, String(body.token_id));
      await SecureStore.setItemAsync(NAME_KEY, body.display_name);
      await SecureStore.setItemAsync(LABEL_KEY, body.label);
      await AsyncStorage.setItem(ADDRESS_KEY, parsed.origin);
      setAccount({
        token: body.token,
        tokenId: String(body.token_id),
        displayName: body.display_name,
        label: body.label,
        origin: parsed.origin,
        userId: null,
      });
      setPassword("");
      setTone("idle");
      setMessage("");
      listPhase.current = "home";
      setPhase("home");
    } catch (error) {
      setTone("error");
      setMessage(
        error.message === "Sign in."
          ? "This server does not accept app sign-in yet."
          : error.message || FAILED,
      );
    } finally {
      setBusy(false);
    }
  }

  function onSignOut() {
    const waiting = hasWaiting(library);
    Alert.alert(
      "Sign out",
      waiting
        ? "Changes waiting on this phone stay here and upload the next time you sign in. Sign out?"
        : "Sign out of Keel on this phone?",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Sign out", style: "destructive", onPress: signOut },
      ],
    );
  }

  async function signOut() {
    if (!account) {
      return;
    }
    setBusy(true);
    try {
      await revokeToken(account.origin, account.token, account.tokenId);
    } catch (error) {
      if (error.status !== 401) {
        setTone("error");
        setMessage(error.message || FAILED);
        setBusy(false);
        return;
      }
    }
    await clearAccount();
    setBusy(false);
  }

  async function clearAccount() {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(TOKEN_ID_KEY);
    await SecureStore.deleteItemAsync(NAME_KEY);
    await SecureStore.deleteItemAsync(LABEL_KEY);
    await SecureStore.deleteItemAsync(USER_ID_KEY);
    setAccount(null);
    setPassword("");
    setMessage("");
    setTone("idle");
    setPhase("signedOut");
  }

  async function persistLibrary(userId, store) {
    setLibrary(store);
    if (userId) {
      await AsyncStorage.setItem(storeKey(userId), JSON.stringify(store));
    }
  }

  async function refreshLibrary(currentAccount, currentStore) {
    const client = {
      profile: () => loadProfile(currentAccount.origin, currentAccount.token),
      snapshots: () => loadSnapshots(currentAccount.origin, currentAccount.token),
      catalog: () => loadCatalog(currentAccount.origin, currentAccount.token),
      read: (path) => read(currentAccount.origin, currentAccount.token, path),
      send: (method, path, body) =>
        send(currentAccount.origin, currentAccount.token, method, path, body),
    };
    const result = await pullLibrary(currentStore, client);
    const userId = String(result.userId);
    if (userId !== currentAccount.userId) {
      await SecureStore.setItemAsync(USER_ID_KEY, userId);
      setAccount({ ...currentAccount, userId });
    }
    await persistLibrary(userId, result.store);
    setWorkError("");
    return result.store;
  }

  async function refreshInbox(currentAccount, currentLibrary) {
    if (!currentAccount.userId) {
      return;
    }
    const projects = Object.values((currentLibrary && currentLibrary.projects) || {}).filter(
      (project) => project.enabled,
    );
    try {
      const issues = await loadInboxIssues(
        currentAccount.origin,
        currentAccount.token,
        projects,
        currentAccount.userId,
      );
      const times = await loadCompletedAt(currentAccount.origin, currentAccount.token, issues);
      setRemoteIssues(issues.map((issue) => ({ ...issue, completedOn: times[issue.id] || null })));
      setInboxMode("online");
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setRemoteIssues(null);
      setInboxMode("offline");
    }
  }

  async function refreshBoard(currentAccount, currentLibrary) {
    const projects = Object.values((currentLibrary && currentLibrary.projects) || {}).filter(
      (project) => project.enabled,
    );
    try {
      const boards = await loadBoards(currentAccount.origin, currentAccount.token, projects);
      setRemoteBoards(boards);
      setBoardMode("online");
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setRemoteBoards(null);
      setBoardMode("offline");
    }
  }

  async function refreshFilterSprints(currentAccount, currentLibrary) {
    const projects = enabledProjects(currentLibrary);
    try {
      const groups = await Promise.all(projects.map(async (project) => {
        const sprints = await read(
          currentAccount.origin,
          currentAccount.token,
          `/api/v1/projects/${project.id}/sprints`,
        );
        return (sprints || []).map((sprint) => ({
          id: sprint.id,
          name: sprint.name,
          state: sprint.state,
          projectId: project.id,
          projectKey: project.key,
        }));
      }));
      setFilterSprints(groups.flat().filter((sprint) => sprint.state !== "completed"));
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
    }
  }

  function filterChoices(projectId) {
    return {
      sprints: sprintOptions(library, filterSprints, projectId),
      projects: projectOptions(library),
      assignees: peopleOptions(library, "unassigned", "Unassigned"),
      reporters: peopleOptions(library, "none", "None"),
      labels: labelOptions(library),
    };
  }

  async function openBoard() {
    listPhase.current = "board";
    setPhase("board");
    setRefreshing(true);
    try {
      const store = await refreshLibrary(account, library);
      const current = store || library;
      await refreshBoard(account, current);
      await refreshFilterSprints(account, current);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setBoardMode("offline");
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  function enabledProjects(store) {
    return Object.values((store && store.projects) || {})
      .filter((project) => project.enabled)
      .sort((left, right) => (left.key || "").localeCompare(right.key || ""));
  }

  async function refreshBacklog(currentAccount, currentLibrary, projectId) {
    const project = enabledProjects(currentLibrary).find((item) => item.id === projectId);
    if (!project) {
      setRemoteBacklog([]);
      setRemoteSprints([]);
      setBacklogMode("online");
      setWorkError("");
      return;
    }
    try {
      const loaded = await loadBacklog(currentAccount.origin, currentAccount.token, project);
      setRemoteBacklog(loaded.issues);
      setRemoteSprints(loaded.sprints);
      setBacklogMode("online");
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setRemoteBacklog(null);
      setRemoteSprints(null);
      setBacklogMode("offline");
    }
  }

  async function openBacklog(projectId) {
    listPhase.current = "backlog";
    setPhase("backlog");
    setRefreshing(true);
    try {
      const store = await refreshLibrary(account, library);
      const current = store || library;
      const projects = enabledProjects(current);
      const chosen = projectId || backlogProjectId || (projects[0] && projects[0].id) || null;
      if (chosen) {
        setBacklogProjectId(chosen);
      }
      await refreshBacklog(account, current, chosen);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setBacklogMode("offline");
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  function savedActiveSprint(store, projectId) {
    const project = enabledProjects(store).find((item) => item.id === projectId);
    if (!project || !project.sprint || project.sprint.state !== "active") {
      return null;
    }
    return project.sprint;
  }

  async function refreshPlanning(currentAccount, currentLibrary, projectId) {
    const project = enabledProjects(currentLibrary).find((item) => item.id === projectId);
    if (!project) {
      setPlanningSprints([]);
      setPlanningMode("online");
      setWorkError("");
      return [];
    }
    try {
      const sprints = await loadProjectSprints(currentAccount.origin, currentAccount.token, project);
      setPlanningSprints(sprints);
      setPlanningMode("online");
      setWorkError("");
      return sprints;
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setPlanningSprints(null);
      setPlanningMode("offline");
      return null;
    }
  }

  async function refreshOpenSprint(currentAccount, currentLibrary, projectId, sprintId) {
    try {
      const detail = await read(currentAccount.origin, currentAccount.token, `/api/v1/sprints/${sprintId}`);
      setOpenSprint(detail);
      setPlanningMode("online");
      return detail;
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      const saved = savedActiveSprint(currentLibrary, projectId);
      setOpenSprint(saved && saved.id === sprintId ? saved : null);
      setPlanningMode("offline");
      return null;
    }
  }

  async function openSprints(projectId) {
    listPhase.current = "sprints";
    setPhase("sprints");
    setSprintNotice("");
    setRefreshing(true);
    try {
      const store = await refreshLibrary(account, library);
      const current = store || library;
      const projects = enabledProjects(current);
      const chosen = projectId || planningProjectId || (projects[0] && projects[0].id) || null;
      if (chosen) {
        setPlanningProjectId(chosen);
      }
      await refreshPlanning(account, current, chosen);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setPlanningMode("offline");
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  async function showSprint(projectId, sprintId) {
    listPhase.current = "sprint";
    setOpenSprint(null);
    setPhase("sprint");
    setSprintNotice("");
    setRefreshing(true);
    try {
      const detail = await refreshOpenSprint(account, library, projectId, sprintId);
      if (detail && detail.state === "active") {
        await refreshFilterSprints(account, library);
      }
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function planSprint(draft) {
    const prepared = prepareSprint(draft);
    if (prepared.error) {
      return prepared.error;
    }
    try {
      await send(account.origin, account.token, "POST", `/api/v1/projects/${planningProjectId}/sprints`, prepared.body);
      await refreshPlanning(account, library, planningProjectId);
      setWorkError("");
      return "";
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return "";
      }
      return err.message || FAILED;
    }
  }

  async function saveSprint(draft) {
    const prepared = prepareSprintUpdate(openSprint, draft);
    if (prepared.error) {
      return prepared.error;
    }
    if (!Object.keys(prepared.changes).length) {
      return "";
    }
    try {
      await send(account.origin, account.token, "PATCH", `/api/v1/sprints/${openSprint.id}`, prepared.changes);
      const store = await refreshLibrary(account, library);
      await refreshPlanning(account, store || library, planningProjectId);
      await refreshOpenSprint(account, store || library, planningProjectId, openSprint.id);
      setWorkError("");
      return "";
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return "";
      }
      return err.message || FAILED;
    }
  }

  async function startOpenSprint() {
    try {
      await send(account.origin, account.token, "POST", `/api/v1/sprints/${openSprint.id}/start`);
      const store = await refreshLibrary(account, library);
      await refreshPlanning(account, store || library, planningProjectId);
      await refreshOpenSprint(account, store || library, planningProjectId, openSprint.id);
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setWorkError(err.message || FAILED);
    }
  }

  async function completeOpenSprint() {
    try {
      const result = await send(account.origin, account.token, "POST", `/api/v1/sprints/${openSprint.id}/complete`);
      const store = await refreshLibrary(account, library);
      const sprints = await refreshPlanning(account, store || library, planningProjectId);
      await refreshOpenSprint(account, store || library, planningProjectId, openSprint.id);
      setSprintNotice(completionNotice(result, sprints || []));
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setWorkError(err.message || FAILED);
    }
  }

  function openFound(jump) {
    if (!jump) {
      return false;
    }
    if (jump.target === "issue" && jump.issueId) {
      listPhase.current = "find";
      setIssueId(jump.issueId);
      setPhase("issue");
      return true;
    }
    if (jump.target === "project" && jump.projectId) {
      openSprints(jump.projectId);
      return true;
    }
    if (jump.target === "sprint" && jump.sprintId) {
      setPlanningProjectId(jump.projectId || null);
      showSprint(jump.projectId, jump.sprintId);
      return true;
    }
    return false;
  }

  function openFind() {
    listPhase.current = "find";
    setPhase("find");
    setFindResult(findView({ library, query: "", payload: null }));
  }

  async function runFind(query) {
    const view = findView({ library, query, payload: null });
    if (view.prompt) {
      setFindResult(view);
      return;
    }
    if (view.jump) {
      openFound(view.jump);
      return;
    }
    try {
      const payload = await read(
        account.origin,
        account.token,
        `/api/v1/search?q=${encodeURIComponent(String(query || "").trim())}`,
      );
      const found = findView({ library, query, payload });
      if (openFound(found.jump)) {
        return;
      }
      setFindResult(found);
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      const fallback = findView({ library, query, payload: null });
      const prefix = err.status === 404
        ? "Find on the server is not available yet."
        : (err.message || FAILED);
      fallback.banner = `${prefix} ${fallback.banner || ""}`.trim();
      setFindResult(fallback);
    }
  }

  async function refreshCalendar(currentAccount, currentLibrary, projectId, when) {
    const projects = enabledProjects(currentLibrary);
    try {
      const issues = await loadCalendarIssues(
        currentAccount.origin,
        currentAccount.token,
        projects,
        Number(currentAccount.userId),
        projectId,
      );
      const times = when === "completed"
        ? await loadCompletedAt(currentAccount.origin, currentAccount.token, issues)
        : null;
      setRemoteCalendar(issues);
      setCompletedAt(times);
      setCalendarLink("online");
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setRemoteCalendar(null);
      setCompletedAt(null);
      setCalendarLink("offline");
    }
  }

  async function openCalendar() {
    listPhase.current = "calendar";
    setPhase("calendar");
    setRefreshing(true);
    try {
      const store = await refreshLibrary(account, library);
      const current = store || library;
      await refreshCalendar(account, current, calendarProjectId, calendarWhen);
      await refreshFilterSprints(account, current);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setCalendarLink("offline");
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  async function refreshSchedules(currentAccount, currentLibrary, projectId) {
    const projects = enabledProjects(currentLibrary);
    const project = projects.find((item) => item.id === projectId) || projects[0];
    if (!project) {
      setRemoteSeries([]);
      setScheduleProjectId(null);
      setScheduleLink("online");
      setWorkError("");
      return;
    }
    setScheduleProjectId(project.id);
    try {
      const series = await read(
        currentAccount.origin,
        currentAccount.token,
        `/api/v1/projects/${project.id}/series`,
      );
      setRemoteSeries(series || []);
      setScheduleLink("online");
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        throw err;
      }
      setRemoteSeries(null);
      setScheduleLink("offline");
    }
  }

  async function openSchedules(projectId) {
    listPhase.current = "schedules";
    setPhase("schedules");
    setScheduleNotice("");
    setRecipe(blankRecipe());
    setRecipeMode("create");
    setRecipeIssue(null);
    setOpenSeries(null);
    setRefreshing(true);
    try {
      const store = await refreshLibrary(account, library);
      await refreshSchedules(account, store || library, projectId || scheduleProjectId);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setScheduleLink("offline");
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  async function showSchedule(seriesId, issue) {
    listPhase.current = issue ? listPhase.current : "schedules";
    setPhase("schedule");
    setRecipeMode(issue ? "occurrence" : "edit");
    setRecipeIssue(issue || null);
    setRecipeScope("series");
    setOpenSeries(null);
    setRecipe(null);
    setRefreshing(true);
    try {
      const series = await read(account.origin, account.token, `/api/v1/series/${seriesId}`);
      let parentKey = "";
      let keepParent = false;
      if (series.parent_id) {
        try {
          const parent = await read(account.origin, account.token, `/api/v1/issues/${series.parent_id}`);
          parentKey = parent.key || "";
        } catch (err) {
          if (err.status === 401) {
            throw err;
          }
          keepParent = true;
        }
      }
      const person = (library.people || []).find((item) => item.id === series.assignee_id);
      setRecipe({
        ...recipeFromSeries(series, {
          parentKey,
          assignee: person ? person.display_name : "",
        }),
        keepParent,
        keepAssignee: Boolean(series.assignee_id) && !person,
      });
      setOpenSeries(series);
      setScheduleProjectId(series.project_id);
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setWorkError(err.message || FAILED);
    } finally {
      setRefreshing(false);
    }
  }

  function openRepeat(issue) {
    setRecipeIssue(issue);
    setRecipe(blankRecipe());
    setRecipeMode("repeat");
    setOpenSeries(null);
    setWorkError("");
    setPhase("schedule");
  }

  function changeRecipe(patch) {
    setRecipe((current) => ({
      ...current,
      ...patch,
      keepParent: patch.parentKey === undefined ? current.keepParent : false,
      keepAssignee: patch.assignee === undefined ? current.keepAssignee : false,
    }));
  }

  async function resolvedEnds(draft) {
    let assigneeId = null;
    const assignee = String(draft.assignee || "").trim();
    if (assignee && !draft.keepAssignee) {
      let people = library.people || [];
      if (!people.length) {
        people = await read(account.origin, account.token, "/api/v1/users");
      }
      const found = (people || []).find(
        (person) => String(person.display_name || "").toLowerCase() === assignee.toLowerCase(),
      );
      if (!found) {
        return { error: "Choose an assignee." };
      }
      assigneeId = found.id;
    }
    let parentId = null;
    const parentKey = String(draft.parentKey || "").trim();
    if (parentKey && !draft.keepParent) {
      let parent = savedIssueId(library, parentKey);
      if (!parent) {
        const parts = issueKeyParts(parentKey);
        if (!parts) {
          return { error: "Choose a parent issue." };
        }
        const projects = await read(account.origin, account.token, "/api/v1/projects");
        const project = (projects || []).find((item) => String(item.key).toUpperCase() === parts.key);
        const issues = project
          ? await read(account.origin, account.token, `/api/v1/projects/${project.id}/issues`)
          : [];
        const found = (issues || []).find((item) => Number(item.number) === parts.number);
        parent = found ? found.id : null;
      }
      if (!parent) {
        return { error: "Choose a parent issue." };
      }
      parentId = parent;
    }
    return { assigneeId, parentId };
  }

  async function saveRecipe() {
    const prepared = prepareRecipe(recipe, { requireTitle: recipeMode !== "repeat" });
    if (prepared.error) {
      return prepared.error;
    }
    try {
      const body = { ...prepared.body };
      if (recipeMode === "repeat") {
        if (!String(recipe.labels || "").trim()) {
          delete body.labels;
        }
        await send(account.origin, account.token, "POST", `/api/v1/projects/${recipeIssue.projectId}/series`, {
          ...body,
          title: recipeIssue.title,
          description: recipeIssue.descriptionText || "",
          type: recipeIssue.type || "story",
          priority: recipeIssue.priority || body.priority,
          parent_id: recipeIssue.parentId,
          assignee_id: recipeIssue.assigneeId,
          seed_issue_id: recipeIssue.id,
        });
        setIssueId(recipeIssue.id);
        setPhase("issue");
        return null;
      }
      if (recipeMode === "occurrence") {
        delete body.type;
        await send(account.origin, account.token, "POST", `/api/v1/issues/${recipeIssue.id}/series`, {
          scope: recipeScope,
          ...body,
        });
        setIssueId(recipeIssue.id);
        setPhase("issue");
        return null;
      }
      const ends = await resolvedEnds(recipe);
      if (ends.error) {
        return ends.error;
      }
      if (!recipe.keepParent) {
        body.parent_id = ends.parentId;
      }
      if (!recipe.keepAssignee) {
        body.assignee_id = ends.assigneeId;
      }
      if (recipeMode === "edit") {
        const updated = await send(account.origin, account.token, "PATCH", `/api/v1/series/${openSeries.id}`, body);
        setOpenSeries(updated);
        setWorkError("");
        return null;
      }
      const created = await send(
        account.origin,
        account.token,
        "POST",
        `/api/v1/projects/${scheduleProjectId}/series`,
        body,
      );
      await showSchedule(created.id);
      return null;
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return null;
      }
      if (err.status === 404 && recipeMode === "occurrence") {
        return "Editing one occurrence from the phone is not available on this server yet.";
      }
      return err.message || FAILED;
    }
  }

  async function pauseSchedule(paused) {
    try {
      const updated = await send(
        account.origin,
        account.token,
        "POST",
        `/api/v1/series/${openSeries.id}/${paused ? "pause" : "resume"}`,
      );
      setOpenSeries(updated);
      setWorkError("");
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setWorkError(err.message || FAILED);
    }
  }

  async function deleteSchedule() {
    try {
      const projectId = openSeries.project_id;
      await send(account.origin, account.token, "DELETE", `/api/v1/series/${openSeries.id}`);
      await openSchedules(projectId);
      setScheduleNotice(DELETED);
    } catch (err) {
      if (err.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setWorkError(err.message || FAILED);
    }
  }

  useEffect(() => {
    const userId = account && account.userId;
    if (!userId) {
      setHomeLayout(account ? blankLayout() : null);
      return undefined;
    }
    let active = true;
    AsyncStorage.getItem(homeKey(userId)).then((raw) => {
      if (active) {
        setHomeLayout(parseLayout(raw));
      }
    });
    return () => {
      active = false;
    };
  }, [account && account.userId]);

  async function rememberHome(next) {
    setHomeLayout(next);
    if (account && account.userId) {
      await AsyncStorage.setItem(homeKey(account.userId), JSON.stringify(next));
    }
  }

  useEffect(() => {
    if (!account) {
      setLibraryReady(false);
      return undefined;
    }
    let active = true;
    (async () => {
      let store = emptyStore();
      if (account.userId) {
        const raw = await AsyncStorage.getItem(storeKey(account.userId));
        if (raw) {
          try {
            store = JSON.parse(raw);
          } catch {
            store = emptyStore();
          }
        }
      }
      if (!active) {
        return;
      }
      setLibrary(store);
      setLibraryReady(true);
      setRefreshing(true);
      try {
        const next = await refreshLibrary(account, store);
        if (active && account.userId) {
          await refreshInbox(account, next || store);
        }
      } catch (err) {
        if (!active) {
          return;
        }
        if (err.status === 401) {
          await clearAccount();
          setTone("error");
          setMessage("Sign in.");
          return;
        }
        if (account.userId) {
          setInboxMode("offline");
        }
        setWorkError(
          workView(store).some((section) => section.saved)
            ? "Showing the saved copy. Could not connect."
            : err.message || FAILED,
        );
      } finally {
        if (active) {
          setRefreshing(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [account && account.token, account && account.origin]);

  async function toggleProject(projectId, enabled) {
    if (!account) {
      return;
    }
    if (!enabled && hasWaiting(library, projectId)) {
      Alert.alert(
        "Stop saving this project?",
        "Waiting changes for this project will be dropped from this phone.",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Turn off",
            style: "destructive",
            onPress: () => persistLibrary(account.userId, dropProject(library, projectId)),
          },
        ],
      );
      return;
    }
    const next = enabled ? enableProject(library, projectId) : dropProject(library, projectId);
    await persistLibrary(account.userId, next);
  }

  async function saveLock(setting) {
    setLockSetting(setting);
    await AsyncStorage.setItem(LOCK_KEY, setting);
  }

  function openSettings() {
    setDraftLabel(account ? account.label : "");
    setMessage("");
    setPhase("settings");
  }

  async function saveLabel() {
    if (!account) {
      return;
    }
    const label = (draftLabel.trim() || deviceLabel()).slice(0, 100);
    setBusy(true);
    try {
      await renameLabel(account.origin, account.token, account.tokenId, label);
      await SecureStore.setItemAsync(LABEL_KEY, label);
      setAccount({ ...account, label });
      setDraftLabel(label);
      setTone("ok");
      setMessage("Phone name saved.");
    } catch (error) {
      if (error.status === 401) {
        await clearAccount();
        setTone("error");
        setMessage("Sign in.");
        return;
      }
      setTone("error");
      setMessage(error.message || FAILED);
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.screen}>
      <StatusBar style="dark" />
      <Text style={styles.title}>Keel</Text>
      {phase === "booting" ? <ActivityIndicator color="#0068B0" /> : null}
      {phase === "locked" ? (
        <View>
          <Text style={styles.message}>Unlock Keel to continue.</Text>
          <PrimaryButton label="Unlock" onPress={promptUnlock} disabled={false} />
        </View>
      ) : null}
      {phase === "signedOut" ? (
        <SignedOut
          address={address}
          username={username}
          password={password}
          busy={busy}
          message={message}
          tone={tone}
          onAddressChange={onAddressChange}
          onUsername={setUsername}
          onPassword={setPassword}
          onCheck={onCheck}
          onSignIn={onSignIn}
        />
      ) : null}
      {phase === "home" && account ? (
        <Home
          account={account}
          busy={busy}
          error={workError}
          inbox={
            account.userId && inboxMode !== "loading" && homeLayout
              ? arrangeInbox(inboxView({
                  library,
                  userId: Number(account.userId),
                  today: localToday(),
                  remote: inboxMode === "online" ? remoteIssues || [] : null,
                  offsetMinutes: new Date().getTimezoneOffset(),
                }), homeLayout)
              : null
          }
          layout={homeLayout}
          onLayout={rememberHome}
          onCreate={() => {
            listPhase.current = "home";
            setMessage("");
            setPhase("create");
          }}
          onOpenIssue={(id) => {
            listPhase.current = "home";
            setIssueId(id);
            setPhase("issue");
          }}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onBoard={openBoard}
          onBacklog={() => openBacklog()}
          onSprints={openSprints}
          onSchedules={openSchedules}
          onFind={openFind}
          onCalendar={openCalendar}
          onRefresh={async () => {
            setRefreshing(true);
            try {
              const store = await refreshLibrary(account, library);
              await refreshInbox(account, store || library);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setWorkError(err.message || FAILED);
            } finally {
              setRefreshing(false);
            }
          }}
          onSettings={() => {
            listPhase.current = "home";
            openSettings();
          }}
          onSignOut={onSignOut}
          onStatus={async (id, status) => {
            if (findIssue(library, id)) {
              const updated = queueUpdate(library, id, { status }, { online: inboxMode === "online" });
              if (updated.error) {
                setWorkError(updated.error);
                return;
              }
              await persistLibrary(account.userId, updated.store);
              try {
                const store = await refreshLibrary(account, updated.store);
                await refreshInbox(account, store || updated.store);
              } catch (err) {
                if (err.status === 401) {
                  await clearAccount();
                  setTone("error");
                  setMessage("Sign in.");
                }
              }
              return;
            }
            try {
              await send(account.origin, account.token, "PATCH", `/api/v1/issues/${id}`, { status });
              await refreshInbox(account, library);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setWorkError(err.message || FAILED);
            }
          }}
          refreshing={refreshing}
        />
      ) : null}
      {phase === "projects" && account ? (
        <Work
          account={account}
          busy={busy}
          error={workError}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onBoard={openBoard}
          onBacklog={() => openBacklog()}
          onSprints={openSprints}
          onSchedules={openSchedules}
          onFind={openFind}
          onCalendar={openCalendar}
          onOpenIssue={(id) => {
            listPhase.current = "projects";
            setIssueId(id);
            setPhase("issue");
          }}
          onCreate={() => {
            listPhase.current = "projects";
            setMessage("");
            setPhase("create");
          }}
          onRefresh={async () => {
            setRefreshing(true);
            try {
              await refreshLibrary(account, library);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setWorkError(err.message || FAILED);
            } finally {
              setRefreshing(false);
            }
          }}
          onSettings={openSettings}
          onSignOut={onSignOut}
          refreshing={refreshing}
          sections={libraryReady ? workView(library) : null}
        />
      ) : null}
      {phase === "board" && account ? (
        <Board
          account={account}
          board={
            boardMode === "loading"
              ? null
              : boardView({
                  library,
                  boards: boardMode === "online" ? remoteBoards || [] : null,
                  projectId: boardProjectId,
                  filter: listFilter,
                })
          }
          busy={busy}
          error={workError}
          filter={listFilter}
          filterChoices={filterChoices(boardProjectId)}
          onFilter={setListFilter}
          showProject={boardProjectId == null}
          onCreate={() => {
            listPhase.current = "board";
            setMessage("");
            setPhase("create");
          }}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onOpenIssue={(id) => {
            listPhase.current = "board";
            setIssueId(id);
            setPhase("issue");
          }}
          onProject={setBoardProjectId}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onBacklog={() => openBacklog()}
          onSprints={openSprints}
          onSchedules={openSchedules}
          onFind={openFind}
          onCalendar={openCalendar}
          onRefresh={openBoard}
          onSettings={() => {
            listPhase.current = "board";
            openSettings();
          }}
          onSignOut={onSignOut}
          onStatus={async (id, status) => {
            if (findIssue(library, id)) {
              const updated = queueUpdate(library, id, { status }, { online: boardMode === "online" });
              if (updated.error) {
                setWorkError(updated.error);
                return;
              }
              await persistLibrary(account.userId, updated.store);
              try {
                const store = await refreshLibrary(account, updated.store);
                await refreshBoard(account, store || updated.store);
              } catch (err) {
                if (err.status === 401) {
                  await clearAccount();
                  setTone("error");
                  setMessage("Sign in.");
                }
              }
              return;
            }
            try {
              await send(account.origin, account.token, "PATCH", `/api/v1/issues/${id}`, { status });
              await refreshBoard(account, library);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setWorkError(err.message || FAILED);
            }
          }}
          refreshing={refreshing}
        />
      ) : null}
      {phase === "backlog" && account ? (
        <Backlog
          account={account}
          backlog={
            backlogMode === "loading"
              ? null
              : backlogView({
                  library,
                  projectId: backlogProjectId,
                  issues: backlogMode === "online" ? remoteBacklog || [] : null,
                  sprints: backlogMode === "online" ? remoteSprints || [] : null,
                })
          }
          busy={busy}
          error={workError}
          onBoard={openBoard}
          onSprints={openSprints}
          onSchedules={openSchedules}
          onFind={openFind}
          onCalendar={openCalendar}
          onCreate={() => {
            listPhase.current = "backlog";
            setMessage("");
            setPhase("create");
          }}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onOpenIssue={(id) => {
            listPhase.current = "backlog";
            setIssueId(id);
            setPhase("issue");
          }}
          onProject={async (id) => {
            setBacklogProjectId(id);
            setRefreshing(true);
            try {
              await refreshBacklog(account, library, id);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            } finally {
              setRefreshing(false);
            }
          }}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onRefresh={() => openBacklog()}
          onSchedule={async (id, sprint) => {
            if (findIssue(library, id)) {
              const updated = queueUpdate(library, id, { sprint_id: sprint.id }, { online: true, sprint });
              if (updated.error) {
                setWorkError(updated.error);
                return;
              }
              await persistLibrary(account.userId, updated.store);
              try {
                const store = await refreshLibrary(account, updated.store);
                await refreshBacklog(account, store || updated.store, backlogProjectId);
              } catch (err) {
                if (err.status === 401) {
                  await clearAccount();
                  setTone("error");
                  setMessage("Sign in.");
                }
              }
              return;
            }
            try {
              await send(account.origin, account.token, "PATCH", `/api/v1/issues/${id}`, { sprint_id: sprint.id });
              const store = await refreshLibrary(account, library);
              await refreshBacklog(account, store || library, backlogProjectId);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setWorkError(err.message || FAILED);
            }
          }}
          onSettings={() => {
            listPhase.current = "backlog";
            openSettings();
          }}
          onSignOut={onSignOut}
          refreshing={refreshing}
        />
      ) : null}
      {phase === "sprints" && account ? (
        <Sprints
          account={account}
          busy={busy}
          error={workError}
          onBacklog={() => openBacklog()}
          onBoard={openBoard}
          onFind={openFind}
          onCalendar={openCalendar}
          onCreate={() => {
            listPhase.current = "sprints";
            setMessage("");
            setPhase("create");
          }}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onOpenSprint={(id) => showSprint(planningProjectId, id)}
          onPlan={planSprint}
          onProject={async (id) => {
            setPlanningProjectId(id);
            setRefreshing(true);
            try {
              await refreshPlanning(account, library, id);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            } finally {
              setRefreshing(false);
            }
          }}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onRefresh={() => openSprints()}
          onSettings={() => {
            listPhase.current = "sprints";
            openSettings();
          }}
          onSignOut={onSignOut}
          planning={
            planningMode === "loading"
              ? null
              : planningView({
                  library,
                  projectId: planningProjectId,
                  sprints: planningMode === "online" ? planningSprints || [] : null,
                })
          }
          refreshing={refreshing}
        />
      ) : null}
      {phase === "sprint" && account ? (
        <SprintScreen
          account={account}
          busy={busy}
          detail={
            openSprint
              ? sprintDetail({
                  library,
                  projectId: planningProjectId,
                  sprint: openSprint,
                  online: planningMode === "online" && Array.isArray(openSprint.issues),
                  filter: openSprint.state === "active" ? listFilter : null,
                })
              : null
          }
          error={workError}
          filter={openSprint && openSprint.state === "active" ? listFilter : null}
          filterChoices={filterChoices(planningProjectId)}
          notice={sprintNotice}
          onFilter={setListFilter}
          onBack={() => {
            listPhase.current = "sprints";
            setPhase("sprints");
          }}
          onComplete={() => {
            Alert.alert(
              "Complete this sprint?",
              "Unfinished issues move to the next planned sprint, or back to the backlog.",
              [
                { text: "Keep it", style: "cancel" },
                { text: "Complete", style: "destructive", onPress: () => completeOpenSprint() },
              ],
            );
          }}
          onOpenIssue={(id) => {
            listPhase.current = "sprint";
            setIssueId(id);
            setPhase("issue");
          }}
          onSave={saveSprint}
          onStart={startOpenSprint}
          refreshing={refreshing}
          onRefresh={() => showSprint(planningProjectId, openSprint && openSprint.id)}
        />
      ) : null}
      {phase === "schedules" && account ? (
        <Schedules
          account={account}
          busy={busy}
          error={workError}
          notice={scheduleNotice}
          onBacklog={() => openBacklog()}
          onBoard={openBoard}
          onCalendar={openCalendar}
          onChange={changeRecipe}
          onCreate={saveRecipe}
          onFind={openFind}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onOpen={(id) => showSchedule(id)}
          onProject={(projectId) => openSchedules(projectId)}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onRefresh={() => openSchedules(scheduleProjectId)}
          onSettings={() => {
            listPhase.current = "schedules";
            openSettings();
          }}
          onSignOut={onSignOut}
          onSprints={openSprints}
          onSchedules={openSchedules}
          projectId={scheduleProjectId}
          projects={enabledProjects(library).map((project) => ({ id: project.id, key: project.key }))}
          recipe={recipe}
          refreshing={refreshing}
          view={
            scheduleLink === "loading"
              ? null
              : seriesView({
                  series: remoteSeries,
                  online: scheduleLink === "online",
                })
          }
        />
      ) : null}
      {phase === "schedule" && account ? (
        <SeriesScreen
          account={account}
          busy={busy}
          error={workError}
          mode={recipeMode}
          onBack={() => {
            if (recipeIssue) {
              setIssueId(recipeIssue.id);
              setPhase("issue");
              return;
            }
            setRecipe(blankRecipe());
            setRecipeMode("create");
            setPhase("schedules");
          }}
          onBacklog={() => openBacklog()}
          onBoard={openBoard}
          onCalendar={openCalendar}
          onChange={changeRecipe}
          onDelete={() => {
            Alert.alert(DELETE_TITLE, DELETE_BODY, [
              { text: "Keep it", style: "cancel" },
              { text: "Delete", style: "destructive", onPress: () => deleteSchedule() },
            ]);
          }}
          onFind={openFind}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onPause={() => pauseSchedule(openSeries && openSeries.state === "active")}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onSave={saveRecipe}
          onScope={setRecipeScope}
          onSettings={() => {
            listPhase.current = "schedule";
            openSettings();
          }}
          onSignOut={onSignOut}
          onSprints={openSprints}
          onSchedules={openSchedules}
          recipe={recipe}
          scope={recipeScope}
          series={openSeries}
        />
      ) : null}
      {phase === "calendar" && account ? (
        <CalendarScreen
          account={account}
          busy={busy}
          calendar={
            calendarLink === "loading"
              ? null
              : calendarView({
                  library,
                  remote: calendarLink === "online" ? remoteCalendar || [] : null,
                  completedAt,
                  mode: calendarWhen,
                  view: calendarViewName,
                  focus: calendarFocus,
                  today: localToday(),
                  projectId: calendarProjectId,
                  userId: Number(account.userId),
                  offsetMinutes: new Date().getTimezoneOffset(),
                  filter: listFilter,
                })
          }
          error={workError}
          filter={listFilter}
          filterChoices={filterChoices(calendarProjectId)}
          onBacklog={() => openBacklog()}
          onBoard={openBoard}
          onFilter={setListFilter}
          showProject={calendarProjectId == null}
          onCreate={() => {
            listPhase.current = "calendar";
            setMessage("");
            setPhase("create");
          }}
          onFind={openFind}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onMode={async (when) => {
            setCalendarWhen(when);
            setRefreshing(true);
            try {
              await refreshCalendar(account, library, calendarProjectId, when);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setCalendarLink("offline");
              setWorkError(err.message || FAILED);
            } finally {
              setRefreshing(false);
            }
          }}
          onMove={(direction) => {
            setCalendarFocus((current) => moveFocus(calendarViewName, current, localToday(), direction));
          }}
          onOpenIssue={(id) => {
            listPhase.current = "calendar";
            setIssueId(id);
            setPhase("issue");
          }}
          onProject={async (projectId) => {
            setCalendarProjectId(projectId);
            setRefreshing(true);
            try {
              await refreshCalendar(account, library, projectId, calendarWhen);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setCalendarLink("offline");
              setWorkError(err.message || FAILED);
            } finally {
              setRefreshing(false);
            }
          }}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onRefresh={async () => {
            setRefreshing(true);
            try {
              const store = await refreshLibrary(account, library);
              await refreshCalendar(account, store || library, calendarProjectId, calendarWhen);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return;
              }
              setCalendarLink("offline");
              setWorkError(err.message || FAILED);
            } finally {
              setRefreshing(false);
            }
          }}
          onSettings={() => {
            listPhase.current = "calendar";
            openSettings();
          }}
          onSignOut={onSignOut}
          onSprints={openSprints}
          onSchedules={openSchedules}
          onView={(next) => {
            setCalendarFocus((current) => focusForView(next, calendarViewName, current, localToday()));
            setCalendarViewName(next);
          }}
          projectId={calendarProjectId}
          refreshing={refreshing}
        />
      ) : null}
      {phase === "find" && account ? (
        <FindScreen
          account={account}
          busy={busy}
          error={workError}
          onBacklog={() => openBacklog()}
          onBoard={openBoard}
          onCalendar={openCalendar}
          onCreate={() => {
            listPhase.current = "find";
            setMessage("");
            setPhase("create");
          }}
          onHome={() => {
            listPhase.current = "home";
            setPhase("home");
          }}
          onOpen={(row) => {
            if (row.target === "issue") {
              listPhase.current = "find";
              setIssueId(row.id);
              setPhase("issue");
              return;
            }
            if (row.target === "project") {
              openSprints(row.projectId);
              return;
            }
            if (row.target === "sprint") {
              setPlanningProjectId(row.projectId || null);
              showSprint(row.projectId, row.id);
            }
          }}
          onProjects={() => {
            listPhase.current = "projects";
            setPhase("projects");
          }}
          onSearch={runFind}
          onSettings={() => {
            listPhase.current = "find";
            openSettings();
          }}
          onSignOut={onSignOut}
          onSprints={openSprints}
          onSchedules={openSchedules}
          result={findResult}
        />
      ) : null}
      {phase === "create" && account ? (
        <CreateIssue
          account={account}
          busy={busy}
          library={library}
          onCancel={() => setPhase(listPhase.current)}
          onFile={async (draft) => {
            const filed = queueCreate(library, draft);
            if (filed.error) {
              return filed.error;
            }
            await persistLibrary(account.userId, filed.store);
            setPhase(listPhase.current);
            try {
              await refreshLibrary(account, filed.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            }
            return null;
          }}
        />
      ) : null}
      {phase === "issue" && account && issueId ? (
        <IssueDetail
          account={account}
          issueId={issueId}
          onBack={() => setPhase(listPhase.current)}
          onDiscard={async (id) => {
            await persistLibrary(account.userId, discardIssue(library, id));
          }}
          onKeepPhone={async (id) => {
            const next = choosePhone(library, id);
            await persistLibrary(account.userId, next);
            try {
              await refreshLibrary(account, next);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
              }
            }
          }}
          onKeepServer={async (id, serverIssue) => {
            await persistLibrary(account.userId, chooseServer(library, id, serverIssue, null));
          }}
          onRecreate={async (id) => {
            const next = queueRecreate(library, id);
            await persistLibrary(account.userId, next);
            try {
              await refreshLibrary(account, next);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
              }
            }
          }}
          onEditSeries={(seriesId, page) => showSchedule(seriesId, page)}
          onRepeat={openRepeat}
          onRemember={async (issue, page) => {
            await persistLibrary(account.userId, rememberDetail(library, issue.id, issue, page));
          }}
          onUpdate={async (id, changes, options) => {
            const updated = queueUpdate(library, id, changes, options);
            if (updated.error) {
              return updated.error;
            }
            await persistLibrary(account.userId, updated.store);
            try {
              await refreshLibrary(account, updated.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            }
            return null;
          }}
          onDelete={async (id) => {
            const removed = queueDelete(library, id);
            if (removed.error) {
              return removed.error;
            }
            await persistLibrary(account.userId, removed.store);
            setPhase(listPhase.current);
            try {
              await refreshLibrary(account, removed.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            }
            return null;
          }}
          onComment={async (id, text) => {
            if (!findIssue(library, id)) {
              const body = String(text || "").trim();
              if (!body) {
                return "A comment needs a body.";
              }
              try {
                await send(account.origin, account.token, "POST", `/api/v1/issues/${id}/comments`, { body });
              } catch (err) {
                if (err.status === 401) {
                  await clearAccount();
                  setTone("error");
                  setMessage("Sign in.");
                }
                return err.message || "Could not connect.";
              }
              return null;
            }
            const added = queueComment(library, id, text, account.displayName);
            if (added.error) {
              return added.error;
            }
            await persistLibrary(account.userId, added.store);
            try {
              await refreshLibrary(account, added.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            }
            return null;
          }}
          onRemoveComment={async (id, commentId) => {
            const removed = queueRemoveComment(library, id, commentId);
            if (removed.error) {
              return removed.error;
            }
            await persistLibrary(account.userId, removed.store);
            try {
              await refreshLibrary(account, removed.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
              }
            }
            return null;
          }}
          onAddChild={async (draft) => {
            const filed = queueCreate(library, draft);
            if (filed.error) {
              return filed.error;
            }
            await persistLibrary(account.userId, filed.store);
            try {
              await refreshLibrary(account, filed.store);
            } catch (err) {
              if (err.status === 401) {
                await clearAccount();
                setTone("error");
                setMessage("Sign in.");
                return "Sign in.";
              }
            }
            return null;
          }}
          onUnauthorized={async () => {
            await clearAccount();
            setTone("error");
            setMessage("Sign in.");
          }}
          library={library}
        />
      ) : null}
      {phase === "settings" && account ? (
        <View>
          <Text style={styles.label}>Lock</Text>
          {LOCK_OPTIONS.map((option) => (
            <Pressable
              key={option.id}
              onPress={() => saveLock(option.id)}
              style={styles.choice}
            >
              <Text style={styles.choiceText}>
                {lockSetting === option.id ? "● " : "○ "}
                {option.title}
              </Text>
            </Pressable>
          ))}
          {!hasDeviceLock ? (
            <Text style={styles.message}>
              This phone has no PIN or fingerprint, so Keel opens without asking.
            </Text>
          ) : null}
          <Text style={styles.label}>Saved projects</Text>
          {libraryReady
            ? Object.values(library.projects)
                .sort((left, right) => left.key.localeCompare(right.key))
                .map((project) => (
                  <View key={project.id} style={styles.projectSwitch}>
                    <Text style={styles.choiceText}>
                      {project.key} · {project.name}
                    </Text>
                    <Switch
                      onValueChange={(enabled) => toggleProject(project.id, enabled)}
                      thumbColor={project.enabled ? "#FFFFFF" : "#8AA0B2"}
                      trackColor={{ false: "#D5E2EC", true: "#0068B0" }}
                      value={project.enabled}
                    />
                  </View>
                ))
            : null}
          <Text style={styles.label}>Phone name</Text>
          <TextInput
            autoCapitalize="words"
            editable={!busy}
            onChangeText={setDraftLabel}
            placeholder={deviceLabel()}
            placeholderTextColor="#8AA0B2"
            style={styles.input}
            value={draftLabel}
          />
          <PrimaryButton label="Save name" onPress={saveLabel} disabled={busy} />
          {message ? (
            <Text style={tone === "ok" ? styles.ok : styles.error}>{message}</Text>
          ) : null}
          <PrimaryButton
            label="Back"
            onPress={() => {
              setMessage("");
              setPhase(listPhase.current);
            }}
            disabled={busy}
          />
        </View>
      ) : null}
    </View>
  );
}

const TYPE_OPTIONS = [
  { id: "epic", title: "Epic" },
  { id: "story", title: "Story" },
  { id: "subtask", title: "Subtask" },
];
const STATUS_OPTIONS = [
  { id: "todo", title: "To Do" },
  { id: "in_progress", title: "In Progress" },
  { id: "in_review", title: "In Review" },
  { id: "blocked", title: "Blocked" },
  { id: "done", title: "Done" },
  { id: "cancelled", title: "Cancelled" },
];
const PRIORITY_OPTIONS = [
  { id: "p1", title: "P1 — Blocker" },
  { id: "p2", title: "P2 — Critical" },
  { id: "p3", title: "P3 — Major" },
  { id: "p4", title: "P4 — Minor" },
  { id: "p5", title: "P5 — Trivial" },
];

function CreateIssue({ account, library, busy, onCancel, onFile }) {
  const projects = Object.values(library.projects || {})
    .filter((project) => project.enabled)
    .sort((left, right) => left.key.localeCompare(right.key));
  const [projectId, setProjectId] = useState(projects[0] ? String(projects[0].id) : "");
  const project = projects.find((item) => String(item.id) === projectId) || null;
  const [type, setType] = useState("story");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("todo");
  const [priority, setPriority] = useState("p4");
  const [assigneeId, setAssigneeId] = useState("");
  const [parentId, setParentId] = useState("");
  const [sprintId, setSprintId] = useState(project && project.sprint ? String(project.sprint.id) : "");
  const [labels, setLabels] = useState("");
  const [estimate, setEstimate] = useState("");
  const [remaining, setRemaining] = useState("");
  const [start, setStart] = useState("");
  const [due, setDue] = useState("");
  const [sprints, setSprints] = useState(project && project.sprint ? [project.sprint] : []);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!project) {
      return undefined;
    }
    setSprintId(project.sprint ? String(project.sprint.id) : "");
    setParentId("");
    let active = true;
    read(account.origin, account.token, `/api/v1/projects/${project.id}/sprints`)
      .then((rows) => {
        if (!active) {
          return;
        }
        const open = (rows || []).filter(
          (row) => row.state === "active" || row.state === "planned",
        );
        setSprints(open.length ? open : project.sprint ? [project.sprint] : []);
      })
      .catch(() => {
        if (active) {
          setSprints(project.sprint ? [project.sprint] : []);
        }
      });
    return () => {
      active = false;
    };
  }, [account.origin, account.token, project && project.id]);

  const expectedParent = type === "story" ? "epic" : type === "subtask" ? "story" : null;
  const parents = expectedParent && project
    ? Object.values(project.issues || {}).filter(
        (issue) => Number(issue.id) > 0 && issue.raw && issue.raw.type === expectedParent,
      )
    : [];

  async function file() {
    const parent = parents.find((issue) => String(issue.id) === parentId);
    const prepared = prepareCreate({
      title,
      projectId: project ? project.id : null,
      type,
      description,
      status,
      priority,
      assigneeId: assigneeId ? Number(assigneeId) : null,
      parent: parent
        ? { id: parent.id, type: parent.raw.type, projectId: project.id }
        : null,
      sprintId: sprintId ? Number(sprintId) : null,
      estimate,
      remaining,
      start,
      due,
      labels,
    });
    if (prepared.error) {
      setError(prepared.error);
      return;
    }
    const failure = await onFile(prepared.draft);
    if (failure) {
      setError(failure);
    }
  }

  if (!projects.length) {
    return (
      <View>
        <Text style={styles.message}>Save a project before creating an issue.</Text>
        <TextButton label="Back" onPress={onCancel} disabled={false} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.workContent} style={styles.work}>
      <TextButton label="Back" onPress={onCancel} disabled={busy} />
      <Text style={styles.sectionHeading}>Create an issue</Text>
      <Text style={styles.label}>Project</Text>
      {projects.map((item) => (
        <Choice
          key={item.id}
          selected={String(item.id) === projectId}
          title={`${item.key} · ${item.name}`}
          onPress={() => setProjectId(String(item.id))}
        />
      ))}
      <Text style={styles.label}>Type</Text>
      {TYPE_OPTIONS.map((item) => (
        <Choice key={item.id} selected={type === item.id} title={item.title} onPress={() => setType(item.id)} />
      ))}
      <Field label="Title" value={title} onChange={setTitle} />
      <Field label="Description" value={description} onChange={setDescription} multiline />
      <Text style={styles.label}>Status</Text>
      {STATUS_OPTIONS.map((item) => (
        <Choice key={item.id} selected={status === item.id} title={item.title} onPress={() => setStatus(item.id)} />
      ))}
      <Text style={styles.label}>Priority</Text>
      {PRIORITY_OPTIONS.map((item) => (
        <Choice
          key={item.id}
          selected={priority === item.id}
          title={item.title}
          onPress={() => setPriority(item.id)}
        />
      ))}
      <Text style={styles.label}>Assignee</Text>
      <Choice selected={assigneeId === ""} title="Unassigned" onPress={() => setAssigneeId("")} />
      {(library.people || []).map((person) => (
        <Choice
          key={person.id}
          selected={assigneeId === String(person.id)}
          title={person.display_name}
          onPress={() => setAssigneeId(String(person.id))}
        />
      ))}
      <Text style={styles.label}>Parent</Text>
      <Choice selected={parentId === ""} title="No parent" onPress={() => setParentId("")} />
      {parents.map((issue) => (
        <Choice
          key={issue.id}
          selected={parentId === String(issue.id)}
          title={`${issue.raw.key} ${issue.raw.title}`}
          onPress={() => setParentId(String(issue.id))}
        />
      ))}
      <Text style={styles.label}>Sprint</Text>
      <Choice selected={sprintId === ""} title="Unscheduled" onPress={() => setSprintId("")} />
      {sprints.map((sprint) => (
        <Choice
          key={sprint.id}
          selected={sprintId === String(sprint.id)}
          title={sprint.name}
          onPress={() => setSprintId(String(sprint.id))}
        />
      ))}
      <Field label="Labels" value={labels} onChange={setLabels} placeholder="hull, deck" />
      <Field label="Estimate" value={estimate} onChange={setEstimate} placeholder="1h 30m" />
      <Field label="Remaining" value={remaining} onChange={setRemaining} placeholder="45m" />
      <Field label="Start" value={start} onChange={setStart} placeholder="2026-10-12 09:00" />
      <Field label="Due" value={due} onChange={setDue} placeholder="2026-10-12 17:00" />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton label="Create issue" onPress={file} disabled={busy} />
    </ScrollView>
  );
}

function EditIssue({ account, issue, library, page, project, onCancel, onSave }) {
  const [type, setType] = useState(issue.type || "story");
  const [title, setTitle] = useState(issue.title || "");
  const [description, setDescription] = useState(issue.description || "");
  const [status, setStatus] = useState(issue.status || "todo");
  const [priority, setPriority] = useState(issue.priority || "p4");
  const [assigneeId, setAssigneeId] = useState(issue.assignee_id ? String(issue.assignee_id) : "");
  const [parentId, setParentId] = useState(issue.parent_id ? String(issue.parent_id) : "");
  const [sprintId, setSprintId] = useState(issue.sprint_id ? String(issue.sprint_id) : "");
  const [labels, setLabels] = useState((issue.labels || []).join(", "));
  const [estimate, setEstimate] = useState(
    issue.estimate_minutes === null || issue.estimate_minutes === undefined
      ? ""
      : formatMinutes(issue.estimate_minutes),
  );
  const [remaining, setRemaining] = useState(
    issue.remaining_minutes === null || issue.remaining_minutes === undefined
      ? ""
      : formatMinutes(issue.remaining_minutes),
  );
  const [start, setStart] = useState(inputWhen(issue.start_at));
  const [due, setDue] = useState(inputWhen(issue.due_at));
  const [sprints, setSprints] = useState(project && project.sprint ? [project.sprint] : []);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!project) {
      return undefined;
    }
    let active = true;
    read(account.origin, account.token, `/api/v1/projects/${project.id}/sprints`)
      .then((rows) => {
        if (!active) {
          return;
        }
        const open = (rows || []).filter((row) => row.state === "active" || row.state === "planned");
        const visible = open.length ? open : project.sprint ? [project.sprint] : [];
        if (issue.sprint_id && !visible.some((row) => row.id === issue.sprint_id)) {
          visible.push({
            id: issue.sprint_id,
            name: (page && page.sprintName) || "Current sprint",
            state: "planned",
          });
        }
        setSprints(visible);
        setConnected(true);
      })
      .catch(() => {
        if (active) {
          setConnected(false);
          setSprints(project.sprint ? [project.sprint] : []);
        }
      });
    return () => {
      active = false;
    };
  }, [account.origin, account.token, project && project.id]);

  const expectedParent = type === "story" ? "epic" : type === "subtask" ? "story" : null;
  const parents = expectedParent && project
    ? Object.values(project.issues || {}).filter(
        (item) => Number(item.id) > 0 && item.id !== issue.id && item.raw && item.raw.type === expectedParent,
      )
    : [];
  if (
    expectedParent &&
    issue.parent_id &&
    page &&
    page.parent &&
    page.parent.id === issue.parent_id &&
    !parents.some((item) => item.id === issue.parent_id)
  ) {
    parents.push({
      id: page.parent.id,
      raw: { key: page.parent.key, title: page.parent.title, type: expectedParent },
    });
  }
  const people = [...(library.people || [])];
  if (issue.assignee_id && !people.some((person) => person.id === issue.assignee_id)) {
    people.push({
      id: issue.assignee_id,
      display_name: page && page.assignee ? page.assignee : "Assignee",
    });
  }

  function ancestorIds(selectedId) {
    const ids = [];
    let current = selectedId;
    const seen = new Set();
    while (current && !seen.has(current)) {
      seen.add(current);
      ids.push(current);
      const found = Object.values((project && project.issues) || {}).find((item) => item.id === current);
      current = found && found.raw ? found.raw.parent_id : null;
    }
    return ids;
  }

  async function save() {
    const parent = parents.find((item) => String(item.id) === parentId);
    const childTypes = project
      ? Object.values(project.issues)
          .filter((item) => item.raw && item.raw.parent_id === issue.id)
          .map((item) => item.raw.type)
      : [];
    const prepared = prepareUpdate({
      issue,
      title,
      projectId: issue.project_id,
      type,
      description,
      status,
      priority,
      assigneeId: assigneeId ? Number(assigneeId) : null,
      parent: parent
        ? { id: parent.id, type: parent.raw.type, projectId: issue.project_id }
        : null,
      ancestorIds: parent ? ancestorIds(parent.id) : [],
      childTypes,
      sprintId: sprintId ? Number(sprintId) : null,
      activeSprintId: project && project.sprint ? project.sprint.id : null,
      online: connected,
      estimate,
      remaining,
      start,
      due,
      labels,
    });
    if (prepared.error) {
      setError(prepared.error);
      return;
    }
    if (!Object.keys(prepared.changes).length) {
      onCancel();
      return;
    }
    const chosen = sprints.find((item) => String(item.id) === sprintId) || null;
    const failure = await onSave(prepared.changes, {
      online: connected,
      sprint: chosen,
      parent: parent ? { ...parent.raw, id: parent.id } : null,
    });
    if (failure) {
      setError(failure);
    }
  }

  const showUnscheduled = connected || !issue.sprint_id;

  return (
    <View>
      <Text style={styles.sectionHeading}>Edit {issue.key || "New"}</Text>
      <Text style={styles.label}>Type</Text>
      {TYPE_OPTIONS.map((item) => (
        <Choice key={item.id} selected={type === item.id} title={item.title} onPress={() => setType(item.id)} />
      ))}
      <Field label="Title" value={title} onChange={setTitle} />
      <Field label="Description" value={description} onChange={setDescription} multiline />
      <Text style={styles.label}>Status</Text>
      {STATUS_OPTIONS.map((item) => (
        <Choice key={item.id} selected={status === item.id} title={item.title} onPress={() => setStatus(item.id)} />
      ))}
      <Text style={styles.label}>Priority</Text>
      {PRIORITY_OPTIONS.map((item) => (
        <Choice key={item.id} selected={priority === item.id} title={item.title} onPress={() => setPriority(item.id)} />
      ))}
      <Text style={styles.label}>Assignee</Text>
      <Choice selected={assigneeId === ""} title="Unassigned" onPress={() => setAssigneeId("")} />
      {people.map((person) => (
        <Choice
          key={person.id}
          selected={assigneeId === String(person.id)}
          title={person.display_name}
          onPress={() => setAssigneeId(String(person.id))}
        />
      ))}
      <Text style={styles.label}>Parent</Text>
      <Choice selected={parentId === ""} title="No parent" onPress={() => setParentId("")} />
      {parents.map((item) => (
        <Choice
          key={item.id}
          selected={parentId === String(item.id)}
          title={`${item.raw.key || "New"} ${item.raw.title}`}
          onPress={() => setParentId(String(item.id))}
        />
      ))}
      <Text style={styles.label}>Sprint</Text>
      {showUnscheduled ? (
        <Choice selected={sprintId === ""} title="Unscheduled" onPress={() => setSprintId("")} />
      ) : null}
      {sprints.map((sprint) => (
        <Choice
          key={sprint.id}
          selected={sprintId === String(sprint.id)}
          title={sprint.name}
          onPress={() => setSprintId(String(sprint.id))}
        />
      ))}
      <Field label="Labels" value={labels} onChange={setLabels} placeholder="hull, deck" />
      <Field label="Estimate" value={estimate} onChange={setEstimate} placeholder="1h 30m" />
      <Field label="Remaining" value={remaining} onChange={setRemaining} placeholder="45m" />
      <Field label="Start" value={start} onChange={setStart} placeholder="2026-10-12 09:00" />
      <Field label="Due" value={due} onChange={setDue} placeholder="2026-10-12 17:00" />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton label="Save" onPress={save} disabled={false} />
    </View>
  );
}

function Choice({ title, selected, onPress }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.choice}>
      <Text style={styles.choiceText}>
        {selected ? "● " : "○ "}
        {title}
      </Text>
    </Pressable>
  );
}

function localToday() {
  const now = new Date();
  const pad = (part) => String(part).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function OptionRow({ label, options, value, onChange }) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.toolbarActions}>
        {options.map(([id, title]) => (
          <TextButton
            key={id}
            label={value === id ? `● ${title}` : title}
            onPress={() => onChange(id)}
            disabled={false}
          />
        ))}
      </View>
    </View>
  );
}

function RecipeFields({ draft, onChange, showIdentity, showType, showPeople, showScope, scope, onScope }) {
  return (
    <View>
      {showScope ? (
        <OptionRow label="Apply to" options={SCOPES} value={scope} onChange={onScope} />
      ) : null}
      {showIdentity ? (
        <View>
          <Field label="Title" value={draft.title} onChange={(title) => onChange({ title })} />
          <Field label="Default description" value={draft.description} onChange={(description) => onChange({ description })} />
          {showType ? (
            <OptionRow
              label="Type"
              options={[["epic", "Epic"], ["story", "Story"], ["subtask", "Subtask"]]}
              value={draft.type}
              onChange={(type) => onChange({ type })}
            />
          ) : null}
          <OptionRow label="Priority" options={PRIORITIES} value={draft.priority} onChange={(priority) => onChange({ priority })} />
          <Field label="Labels" value={draft.labels} onChange={(labels) => onChange({ labels })} placeholder="hull, deck" />
        </View>
      ) : null}
      {showPeople ? (
        <View>
          <Field label="Assignee" value={draft.assignee} onChange={(assignee) => onChange({ assignee })} placeholder="Unassigned" />
          <Field label="Parent" value={draft.parentKey} onChange={(parentKey) => onChange({ parentKey })} placeholder="KEEL-12" />
        </View>
      ) : null}
      <OptionRow label="When to create the next copy" options={SPAWNS} value={draft.spawnMode} onChange={(spawnMode) => onChange({ spawnMode })} />
      <OptionRow label="Put copies in the sprint overlapping" options={BASES} value={draft.sprintBasis} onChange={(sprintBasis) => onChange({ sprintBasis })} />
      <Field label="Look-ahead" value={draft.lookAhead} onChange={(lookAhead) => onChange({ lookAhead })} />
      <Text style={styles.message}>Leave start or due blank and copies are created without that date.</Text>
      <Field label="Start offset (days before)" value={draft.startOffset} onChange={(startOffset) => onChange({ startOffset })} />
      <Field label="Start time" value={draft.startTime} onChange={(startTime) => onChange({ startTime })} placeholder="09:00" />
      <Field label="Due offset (days after)" value={draft.dueOffset} onChange={(dueOffset) => onChange({ dueOffset })} />
      <Field label="Due time" value={draft.dueTime} onChange={(dueTime) => onChange({ dueTime })} placeholder="17:00" />
      <OptionRow label="Repeat" options={FREQS} value={draft.freq} onChange={(freq) => onChange({ freq })} />
      <Field label="Every" value={draft.interval} onChange={(interval) => onChange({ interval })} />
      <Field label="Starts" value={draft.startsOn} onChange={(startsOn) => onChange({ startsOn })} placeholder="YYYY-MM-DD" />
      <Text style={styles.label}>Weekdays</Text>
      <View style={styles.toolbarActions}>
        {WEEKDAYS.map((name, index) => (
          <TextButton
            key={name}
            label={draft.weekdays.includes(index) ? `● ${name}` : name}
            onPress={() => onChange({
              weekdays: draft.weekdays.includes(index)
                ? draft.weekdays.filter((day) => day !== index)
                : [...draft.weekdays, index],
            })}
            disabled={false}
          />
        ))}
      </View>
      <Field label="Day of month" value={draft.monthDay} onChange={(monthDay) => onChange({ monthDay })} />
      <OptionRow
        label="Month"
        options={[["", "From start date"], ...MONTHS.map((name, index) => [String(index + 1), name])]}
        value={draft.month}
        onChange={(month) => onChange({ month })}
      />
      <Field label="Nth weekday (1–4 or -1 for last)" value={draft.nthWeek} onChange={(nthWeek) => onChange({ nthWeek })} />
      <OptionRow
        label="Ends"
        options={[["never", "Never"], ["on", "On a date"], ["count", "After a count"]]}
        value={draft.endMode}
        onChange={(endMode) => onChange({ endMode })}
      />
      {draft.endMode === "on" ? (
        <Field label="End date" value={draft.endsOn} onChange={(endsOn) => onChange({ endsOn })} placeholder="YYYY-MM-DD" />
      ) : null}
      {draft.endMode === "count" ? (
        <Field label="Occurrence count" value={draft.occurrenceCount} onChange={(occurrenceCount) => onChange({ occurrenceCount })} />
      ) : null}
    </View>
  );
}

function Schedules({
  account,
  view,
  projects,
  projectId,
  recipe,
  busy,
  error,
  notice,
  refreshing,
  onRefresh,
  onProject,
  onOpen,
  onCreate,
  onChange,
  onHome,
  onProjects,
  onBoard,
  onBacklog,
  onSprints,
  onCalendar,
  onFind,
  onSettings,
  onSignOut,
}) {
  const [formError, setFormError] = useState("");
  const online = view && !view.banner;
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>Schedules</Text>
      <View style={styles.toolbarActions}>
        {projects.map((project) => (
          <TextButton
            key={project.id}
            label={projectId === project.id ? `● ${project.key}` : project.key}
            onPress={() => onProject(project.id)}
            disabled={busy}
          />
        ))}
      </View>
      {view === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {notice ? <Text style={styles.message}>{notice}</Text> : null}
      {view && view.banner ? <Text style={styles.message}>{view.banner}</Text> : null}
      {view && view.empty ? <Text style={styles.message}>{view.empty}</Text> : null}
      {view
        ? view.rows.map((row) => (
            <Pressable key={row.id} accessibilityRole="button" onPress={() => onOpen(row.id)} style={styles.issue}>
              <Text style={styles.issueKey}>{row.title}</Text>
              <Text style={styles.issueTitle}>{row.summary}</Text>
              <Text style={styles.issueStatus}>{row.typeLabel} · {row.stateLabel}</Text>
            </Pressable>
          ))
        : null}
      {online && projectId ? (
        <View style={styles.project}>
          <Text style={styles.projectName}>New series</Text>
          {formError ? <Text style={styles.error}>{formError}</Text> : null}
          <RecipeFields draft={recipe} onChange={onChange} showIdentity showType showPeople />
          <PrimaryButton
            label="Create series"
            disabled={busy}
            onPress={async () => {
              const failure = await onCreate();
              setFormError(failure || "");
            }}
          />
        </View>
      ) : null}
    </ScrollView>
  );
}

function SeriesScreen({
  account,
  series,
  recipe,
  mode,
  scope,
  busy,
  error,
  onChange,
  onScope,
  onSave,
  onPause,
  onDelete,
  onBack,
  onHome,
  onProjects,
  onBoard,
  onBacklog,
  onSprints,
  onCalendar,
  onFind,
  onSettings,
  onSignOut,
}) {
  const [formError, setFormError] = useState("");
  const ready = mode === "repeat" || series;
  const title = mode === "repeat" ? "Make this repeating" : mode === "occurrence" ? "Edit series" : (series && series.title) || "Schedule";
  return (
    <ScrollView contentContainerStyle={styles.workContent} style={styles.work}>
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Back" onPress={onBack} disabled={busy} />
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>{title}</Text>
      {series ? (
        <Text style={styles.message}>{series.cadence_summary}. {series.state === "paused" ? "Paused" : "Active"}.</Text>
      ) : null}
      {mode === "edit" && series ? (
        <View style={styles.toolbarActions}>
          <TextButton
            label={series.state === "active" ? "Pause" : "Resume"}
            onPress={onPause}
            disabled={busy}
          />
          <TextButton label="Delete" onPress={onDelete} disabled={busy} />
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {formError ? <Text style={styles.error}>{formError}</Text> : null}
      {ready ? null : <ActivityIndicator color="#0068B0" />}
      {ready && recipe ? (
        <RecipeFields
          draft={recipe}
          onChange={onChange}
          onScope={onScope}
          scope={scope}
          showIdentity={mode !== "repeat"}
          showType={mode === "create" || mode === "edit"}
          showPeople={mode === "create" || mode === "edit"}
          showScope={mode === "occurrence"}
        />
      ) : null}
      {ready ? (
      <PrimaryButton
        label={mode === "repeat" ? "Make this repeating" : "Save recipe"}
        disabled={busy}
        onPress={async () => {
          const failure = await onSave();
          setFormError(failure || "");
        }}
      />
      ) : null}
    </ScrollView>
  );
}

function CalendarIssue({ issue, onPress }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.issue}>
      <Text style={[styles.issueKey, { color: issue.color }]}>{issue.key || "New"}</Text>
      <Text style={styles.issueTitle}>{issue.title}</Text>
      <Text style={styles.issueStatus}>{issue.statusLabel}</Text>
      {issue.time ? <Text style={styles.issueStatus}>{issue.time}</Text> : null}
      {issue.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
    </Pressable>
  );
}

function CalendarScreen({
  account,
  calendar,
  busy,
  error,
  filter,
  filterChoices,
  showProject,
  onFilter,
  refreshing,
  onRefresh,
  projectId,
  onView,
  onMode,
  onMove,
  onProject,
  onOpenIssue,
  onCreate,
  onHome,
  onProjects,
  onBoard,
  onBacklog,
  onSprints,
  onSchedules,
  onFind,
  onSettings,
  onSignOut,
}) {
  const selected = (current, value, label) => (current === value ? `● ${label}` : label);
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>Calendar</Text>
      <View style={styles.toolbarActions}>
        <TextButton label={selected(calendar && calendar.view, "month", "Month")} onPress={() => onView("month")} disabled={busy} />
        <TextButton label={selected(calendar && calendar.view, "week", "Week")} onPress={() => onView("week")} disabled={busy} />
        <TextButton label={selected(calendar && calendar.view, "day", "Day")} onPress={() => onView("day")} disabled={busy} />
      </View>
      <View style={styles.toolbarActions}>
        <TextButton label={selected(calendar && calendar.mode, "start", "Start to due")} onPress={() => onMode("start")} disabled={busy} />
        <TextButton label={selected(calendar && calendar.mode, "completed", "Completed")} onPress={() => onMode("completed")} disabled={busy} />
        <TextButton label={selected(calendar && calendar.mode, "created", "Created")} onPress={() => onMode("created")} disabled={busy} />
      </View>
      <View style={styles.toolbarActions}>
        <TextButton label="Previous" onPress={() => onMove(-1)} disabled={busy} />
        <TextButton label="Today" onPress={() => onMove("today")} disabled={busy} />
        <TextButton label="Next" onPress={() => onMove(1)} disabled={busy} />
      </View>
      {calendar ? (
        <View style={styles.toolbarActions}>
          <TextButton label={projectId == null ? "● Mine" : "Mine"} onPress={() => onProject(null)} disabled={busy} />
          {calendar.projects.map((project) => (
            <TextButton
              key={project.id}
              label={projectId === project.id ? `● ${project.key}` : project.key}
              onPress={() => onProject(project.id)}
              disabled={busy}
            />
          ))}
        </View>
      ) : null}
      <FilterBar filter={filter} choices={filterChoices} showProject={showProject} onChange={onFilter} />
      <Text style={styles.projectName}>{calendar ? calendar.label : ""}</Text>
      {calendar === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {calendar && calendar.banner ? <Text style={styles.message}>{calendar.banner}</Text> : null}
      {calendar && calendar.empty ? <Text style={styles.message}>{calendar.empty}</Text> : null}
      {calendar && calendar.view === "month" ? (
        <View>
          <View style={styles.calendarWeek}>
            {calendar.weekdays.map((name) => (
              <Text key={name} style={styles.calendarWeekday}>{name}</Text>
            ))}
          </View>
          {calendar.weeks.map((week) => (
            <View key={week.days[0].date} style={styles.calendarWeek}>
              {week.days.map((day) => (
                <View
                  key={day.date}
                  style={[styles.calendarDay, !day.inMonth && styles.calendarMuted, day.isToday && styles.calendarToday]}
                >
                  <Text style={styles.calendarDate}>{day.number}</Text>
                  {day.issues.map((issue) => (
                    <Pressable key={issue.id} accessibilityRole="button" onPress={() => onOpenIssue(issue.id)}>
                      <Text numberOfLines={1} style={[styles.calendarChip, { color: issue.color }]}>{issue.key || "New"}</Text>
                      <Text numberOfLines={1} style={styles.calendarStatus}>{issue.statusLabel}</Text>
                    </Pressable>
                  ))}
                </View>
              ))}
            </View>
          ))}
        </View>
      ) : null}
      {calendar && calendar.view !== "month"
        ? calendar.days.map((day) => (
            <View key={day.date} style={styles.project}>
              {calendar.view === "week" ? <Text style={styles.projectName}>{day.heading}</Text> : null}
              {day.issues.length
                ? day.issues.map((issue) => (
                    <CalendarIssue key={issue.id} issue={issue} onPress={() => onOpenIssue(issue.id)} />
                  ))
                : null}
            </View>
          ))
        : null}
    </ScrollView>
  );
}

function Home({
  account,
  inbox,
  busy,
  error,
  refreshing,
  onRefresh,
  onOpenIssue,
  onStatus,
  onCreate,
  onProjects,
  onBoard,
  onBacklog,
  onSprints,
  onSchedules,
  onFind,
  onCalendar,
  onSettings,
  onSignOut,
  layout,
  onLayout,
}) {
  const [openStatus, setOpenStatus] = useState(null);
  const visible = inbox ? inbox.sections.map((section) => section.key) : [];
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>Home</Text>
      {inbox === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {inbox && inbox.banner ? <Text style={styles.message}>{inbox.banner}</Text> : null}
      {inbox && inbox.empty ? <Text style={styles.message}>{inbox.empty}</Text> : null}
      {inbox && inbox.allHidden ? <Text style={styles.message}>{inbox.allHidden}</Text> : null}
      {inbox
        ? inbox.sections.map((section) => (
            <View key={section.key} style={styles.project}>
              <Text style={styles.projectName}>{section.title}</Text>
              <View style={styles.toolbarActions}>
                <TextButton
                  label="Up"
                  onPress={() => onLayout(moveSection(layout, visible, section.key, "up"))}
                  disabled={busy}
                />
                <TextButton
                  label="Down"
                  onPress={() => onLayout(moveSection(layout, visible, section.key, "down"))}
                  disabled={busy}
                />
                <TextButton
                  label="Remove"
                  onPress={() => onLayout(hideSection(layout, section.key))}
                  disabled={busy}
                />
              </View>
              {section.needsConnection ? <Text style={styles.message}>{inbox.needsConnection}</Text> : null}
              {section.rows.map((row) => (
                <View key={`${section.key}-${row.id}`} style={styles.issue}>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => onOpenIssue(row.id)}
                  >
                    <Text style={styles.issueKey}>
                      {row.key || "New"}
                      {row.projectKey ? ` · ${row.projectKey}` : ""}
                    </Text>
                    <Text style={styles.issueTitle}>{row.title}</Text>
                    {row.blockers ? (
                      <Text style={styles.issueStatus}>Blocked by {row.blockers}</Text>
                    ) : null}
                    {row.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
                  </Pressable>
                  <TextButton
                    label={row.statusLabel}
                    onPress={() => setOpenStatus(openStatus === `${section.key}-${row.id}` ? null : `${section.key}-${row.id}`)}
                    disabled={busy}
                  />
                  {openStatus === `${section.key}-${row.id}`
                    ? STATUS_OPTIONS.map((option) => (
                        <Choice
                          key={option.id}
                          selected={row.status === option.id}
                          title={option.title}
                          onPress={() => {
                            setOpenStatus(null);
                            if (option.id !== row.status) {
                              onStatus(row.id, option.id);
                            }
                          }}
                        />
                      ))
                    : null}
                </View>
              ))}
            </View>
          ))
        : null}
      {inbox && inbox.hidden && inbox.hidden.length ? (
        <View style={styles.project}>
          <Text style={styles.projectName}>Add a panel</Text>
          <View style={styles.toolbarActions}>
            {inbox.hidden.map((panel) => (
              <TextButton
                key={panel.key}
                label={panel.title}
                onPress={() => onLayout(showSection(layout, panel.key))}
                disabled={busy}
              />
            ))}
          </View>
        </View>
      ) : null}
    </ScrollView>
  );
}

function FindScreen({
  account,
  result,
  busy,
  error,
  onSearch,
  onOpen,
  onHome,
  onProjects,
  onBoard,
  onBacklog,
  onSprints,
  onSchedules,
  onCalendar,
  onCreate,
  onSettings,
  onSignOut,
}) {
  const [query, setQuery] = useState("");
  return (
    <ScrollView contentContainerStyle={styles.workContent} style={styles.work}>
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>Find</Text>
      <TextInput
        style={styles.input}
        value={query}
        onChangeText={setQuery}
        placeholder="Issue key or words"
        autoCapitalize="none"
        autoCorrect={false}
        onSubmitEditing={() => onSearch(query)}
      />
      <PrimaryButton label="Search" disabled={busy} onPress={() => onSearch(query)} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {result && result.prompt ? <Text style={styles.message}>{result.prompt}</Text> : null}
      {result && result.banner ? <Text style={styles.message}>{result.banner}</Text> : null}
      {result
        ? result.sections.filter((section) => !section.needsConnection || section.rows.length).map((section) => (
            <View key={section.key} style={styles.project}>
              <Text style={styles.projectName}>{section.label}</Text>
              {section.empty ? <Text style={styles.message}>{section.empty}</Text> : null}
              {section.rows.map((row, index) => (
                <Pressable
                  key={`${section.key}-${row.id || index}`}
                  accessibilityRole={row.target === "user" ? "text" : "button"}
                  onPress={row.target === "user" ? undefined : () => onOpen(row)}
                  style={styles.issue}
                >
                  <Text style={styles.issueKey}>{row.title}</Text>
                  {row.detail ? <Text style={styles.issueTitle}>{row.detail}</Text> : null}
                  {row.meta ? <Text style={styles.issueStatus}>{row.meta}</Text> : null}
                  {row.snippet ? <Text style={styles.issueStatus}>{row.snippet}</Text> : null}
                </Pressable>
              ))}
              {section.more ? <Text style={styles.message}>{section.more}</Text> : null}
            </View>
          ))
        : null}
    </ScrollView>
  );
}

function Sprints({
  account,
  planning,
  busy,
  error,
  refreshing,
  onRefresh,
  onOpenSprint,
  onPlan,
  onProject,
  onCreate,
  onHome,
  onProjects,
  onBoard,
  onBacklog,
  onFind,
  onCalendar,
  onSettings,
  onSignOut,
}) {
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [formError, setFormError] = useState("");
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>{planning ? planning.title : "Sprints"}</Text>
      {planning ? (
        <View style={styles.toolbarActions}>
          {planning.projects.map((project) => (
            <TextButton key={project.id} label={project.key} onPress={() => onProject(project.id)} disabled={busy} />
          ))}
        </View>
      ) : null}
      {planning === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {planning && planning.banner ? <Text style={styles.message}>{planning.banner}</Text> : null}
      {planning
        ? planning.sections.map((section) => (
            <View key={section.key} style={styles.project}>
              <Text style={styles.projectName}>{section.label}</Text>
              {section.needsConnection ? <Text style={styles.message}>{NEEDS_CONNECTION}</Text> : null}
              {section.empty ? <Text style={styles.message}>{section.empty}</Text> : null}
              {section.sprints.map((sprint) => (
                <Pressable key={sprint.id} accessibilityRole="button" onPress={() => onOpenSprint(sprint.id)} style={styles.issue}>
                  <Text style={styles.issueKey}>{sprint.name}</Text>
                  {sprint.goal ? <Text style={styles.issueTitle}>{sprint.goal}</Text> : null}
                  {sprint.starts || sprint.ends ? (
                    <Text style={styles.issueStatus}>
                      {sprint.starts || "No start"} · {sprint.ends || "No end"}
                    </Text>
                  ) : null}
                </Pressable>
              ))}
            </View>
          ))
        : null}
      {planning && planning.canPlan ? (
        <View style={styles.project}>
          <Text style={styles.projectName}>Plan a sprint</Text>
          {formError ? <Text style={styles.error}>{formError}</Text> : null}
          <Text style={styles.label}>Name</Text>
          <TextInput style={styles.input} value={name} onChangeText={setName} maxLength={200} />
          <Text style={styles.label}>Goal</Text>
          <TextInput style={styles.input} value={goal} onChangeText={setGoal} />
          <Text style={styles.label}>Starts</Text>
          <TextInput style={styles.input} value={startsOn} onChangeText={setStartsOn} placeholder="YYYY-MM-DD" />
          <Text style={styles.label}>Ends</Text>
          <TextInput style={styles.input} value={endsOn} onChangeText={setEndsOn} placeholder="YYYY-MM-DD" />
          <PrimaryButton
            label="Create sprint"
            disabled={busy}
            onPress={async () => {
              const failure = await onPlan({ name, goal, startsOn, endsOn });
              setFormError(failure || "");
              if (!failure) {
                setName("");
                setGoal("");
                setStartsOn("");
                setEndsOn("");
              }
            }}
          />
        </View>
      ) : null}
    </ScrollView>
  );
}

function SprintScreen({
  account,
  detail,
  busy,
  error,
  filter,
  filterChoices,
  onFilter,
  notice,
  refreshing,
  onRefresh,
  onBack,
  onOpenIssue,
  onStart,
  onComplete,
  onSave,
}) {
  const [name, setName] = useState(detail ? detail.name : "");
  const [goal, setGoal] = useState(detail ? detail.goal : "");
  const [startsOn, setStartsOn] = useState(detail ? detail.starts : "");
  const [endsOn, setEndsOn] = useState(detail ? detail.ends : "");
  const [formError, setFormError] = useState("");
  useEffect(() => {
    setName(detail ? detail.name : "");
    setGoal(detail ? detail.goal : "");
    setStartsOn(detail ? detail.starts : "");
    setEndsOn(detail ? detail.ends : "");
    setFormError("");
  }, [detail && detail.id, detail && detail.name, detail && detail.goal, detail && detail.starts, detail && detail.ends]);
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Back" onPress={onBack} disabled={busy} />
        </View>
      </View>
      {detail === null && refreshing ? <ActivityIndicator color="#0068B0" /> : null}
      {detail === null && !refreshing ? <Text style={styles.message}>{NEEDS_CONNECTION}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {notice ? <Text style={styles.message}>{notice}</Text> : null}
      {detail ? (
        <View>
          <Text style={styles.sectionHeading}>{detail.name}</Text>
          <Text style={styles.message}>
            {detail.stateLabel}
            {detail.goal ? ` — ${detail.goal}` : ""}
          </Text>
          {detail.starts || detail.ends ? (
            <Text style={styles.message}>
              Starts {detail.starts || "none"} · Ends {detail.ends || "none"}
            </Text>
          ) : null}
          {detail.canStart ? <PrimaryButton label="Start sprint" onPress={onStart} disabled={busy} /> : null}
          {detail.canComplete ? <PrimaryButton label="Complete sprint" onPress={onComplete} disabled={busy} /> : null}
          <FilterBar filter={filter} choices={filterChoices} showProject={false} onChange={onFilter} />
          {detail.empty ? <Text style={styles.message}>{detail.empty}</Text> : null}
          {detail.rows.map((row) => (
            <Pressable key={row.id} accessibilityRole="button" onPress={() => onOpenIssue(row.id)} style={styles.issue}>
              <Text style={styles.issueKey}>{row.key || "New"}</Text>
              <Text style={styles.issueTitle}>{row.title}</Text>
              <Text style={styles.issueStatus}>
                {row.typeLabel} · {row.priority} · {row.statusLabel} · {row.assignee}
              </Text>
              {row.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
            </Pressable>
          ))}
          {detail.editable ? (
            <View style={styles.project}>
              <Text style={styles.projectName}>Sprint settings</Text>
              {formError ? <Text style={styles.error}>{formError}</Text> : null}
              <Text style={styles.label}>Name</Text>
              <TextInput style={styles.input} value={name} onChangeText={setName} maxLength={200} />
              <Text style={styles.label}>Goal</Text>
              <TextInput style={styles.input} value={goal} onChangeText={setGoal} />
              <Text style={styles.label}>Starts</Text>
              <TextInput style={styles.input} value={startsOn} onChangeText={setStartsOn} placeholder="YYYY-MM-DD" />
              <Text style={styles.label}>Ends</Text>
              <TextInput style={styles.input} value={endsOn} onChangeText={setEndsOn} placeholder="YYYY-MM-DD" />
              <PrimaryButton
                label="Save"
                disabled={busy}
                onPress={async () => {
                  const failure = await onSave({ name, goal, startsOn, endsOn });
                  setFormError(failure || "");
                }}
              />
            </View>
          ) : null}
        </View>
      ) : null}
    </ScrollView>
  );
}

function Backlog({
  account,
  backlog,
  busy,
  error,
  refreshing,
  onRefresh,
  onOpenIssue,
  onSchedule,
  onProject,
  onCreate,
  onHome,
  onProjects,
  onBoard,
  onSprints,
  onSchedules,
  onFind,
  onCalendar,
  onSettings,
  onSignOut,
}) {
  const [openSchedule, setOpenSchedule] = useState(null);
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>{backlog ? backlog.title : "Backlog"}</Text>
      {backlog ? (
        <View style={styles.toolbarActions}>
          {backlog.projects.map((project) => (
            <TextButton
              key={project.id}
              label={project.key}
              onPress={() => onProject(project.id)}
              disabled={busy}
            />
          ))}
        </View>
      ) : null}
      {backlog === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {backlog && backlog.banner ? <Text style={styles.message}>{backlog.banner}</Text> : null}
      {backlog && backlog.empty ? <Text style={styles.message}>{backlog.empty}</Text> : null}
      {backlog && backlog.noSprint ? <Text style={styles.message}>{backlog.noSprint}</Text> : null}
      {backlog
        ? backlog.rows.map((row) => (
            <View key={row.id} style={styles.issue}>
              <Pressable accessibilityRole="button" onPress={() => onOpenIssue(row.id)}>
                <Text style={styles.issueKey}>{row.key || "New"}</Text>
                <Text style={styles.issueTitle}>{row.title}</Text>
                <Text style={styles.issueStatus}>
                  {row.typeLabel} · {row.priority} · {row.statusLabel} · {row.assignee}
                </Text>
                {row.start ? <Text style={styles.issueStatus}>Start {row.start}</Text> : null}
                {row.due ? <Text style={styles.issueStatus}>Due {row.due}</Text> : null}
                {row.blockers ? (
                  <Text style={styles.issueStatus}>
                    {row.blockers} blocker{row.blockers === 1 ? "" : "s"}
                  </Text>
                ) : null}
                {row.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
              </Pressable>
              {backlog.sprints.length ? (
                <TextButton
                  label="Schedule"
                  onPress={() => setOpenSchedule(openSchedule === row.id ? null : row.id)}
                  disabled={busy}
                />
              ) : null}
              {openSchedule === row.id
                ? backlog.sprints.map((sprint) => (
                    <Choice
                      key={sprint.id}
                      selected={false}
                      title={sprint.label}
                      onPress={() => {
                        setOpenSchedule(null);
                        onSchedule(row.id, sprint);
                      }}
                    />
                  ))
                : null}
            </View>
          ))
        : null}
    </ScrollView>
  );
}

function FilterBar({ filter, choices, showProject, onChange }) {
  const [open, setOpen] = useState("");
  if (!filter) {
    return null;
  }
  const menus = filterMenus(filter, choices || {}, showProject);
  const current = menus.find((menu) => menu.id === open);
  return (
    <View>
      <View style={styles.toolbarActions}>
        {menus.map((menu) => (
          <TextButton
            key={menu.id}
            label={open === menu.id ? `● ${menu.title}: ${menu.summary}` : `${menu.title}: ${menu.summary}`}
            onPress={() => setOpen(open === menu.id ? "" : menu.id)}
            disabled={false}
          />
        ))}
        <TextButton
          label="Reset all"
          onPress={() => {
            onChange(blankFilter());
            setOpen("");
          }}
          disabled={false}
        />
      </View>
      {current ? (
        <View style={styles.toolbarActions}>
          {current.options.map(([value, label]) => (
            <TextButton
              key={value}
              label={(filter[current.id] || []).includes(value) ? `● ${label}` : label}
              onPress={() => onChange(toggleChoice(filter, current.id, value))}
              disabled={false}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function Board({
  account,
  board,
  busy,
  error,
  filter,
  filterChoices,
  showProject,
  onFilter,
  refreshing,
  onRefresh,
  onOpenIssue,
  onStatus,
  onProject,
  onCreate,
  onHome,
  onProjects,
  onBacklog,
  onSprints,
  onSchedules,
  onFind,
  onCalendar,
  onSettings,
  onSignOut,
}) {
  const [openMove, setOpenMove] = useState(null);
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0068B0" />}
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Projects" onPress={onProjects} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      <Text style={styles.sectionHeading}>{board ? board.title : "Board"}</Text>
      {board ? (
        <View style={styles.toolbarActions}>
          <TextButton label="All" onPress={() => onProject(null)} disabled={busy} />
          {board.projects.map((project) => (
            <TextButton
              key={project.id}
              label={project.key}
              onPress={() => onProject(project.id)}
              disabled={busy}
            />
          ))}
        </View>
      ) : null}
      <FilterBar filter={filter} choices={filterChoices} showProject={showProject} onChange={onFilter} />
      {board === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {board && board.banner ? <Text style={styles.message}>{board.banner}</Text> : null}
      {board && board.empty ? <Text style={styles.message}>{board.empty}</Text> : null}
      {board ? (
        <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator style={styles.boardRow}>
          {board.columns.map((column) => (
            <View key={column.status} style={styles.boardColumn}>
              <Text style={styles.projectName}>
                {column.label} {column.cards.length}
              </Text>
              {column.cards.map((card) => (
                <View key={card.id} style={styles.issue}>
                  <Pressable accessibilityRole="button" onPress={() => onOpenIssue(card.id)}>
                    <Text style={styles.issueKey}>{card.key || "New"}</Text>
                    <Text style={styles.issueTitle}>{card.title}</Text>
                    <Text style={styles.issueStatus}>
                      {card.typeLabel} · {card.priority} · {card.assignee}
                    </Text>
                    {card.sprintName ? <Text style={styles.issueStatus}>{card.sprintName}</Text> : null}
                    {card.blockers ? (
                      <Text style={styles.issueStatus}>
                        {card.blockers} blocker{card.blockers === 1 ? "" : "s"}
                      </Text>
                    ) : null}
                    {card.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
                  </Pressable>
                  <TextButton
                    label="Move"
                    onPress={() => setOpenMove(openMove === card.id ? null : card.id)}
                    disabled={busy}
                  />
                  {openMove === card.id
                    ? STATUS_OPTIONS.map((option) => (
                        <Choice
                          key={option.id}
                          selected={card.status === option.id}
                          title={option.title}
                          onPress={() => {
                            setOpenMove(null);
                            if (option.id !== card.status) {
                              onStatus(card.id, option.id);
                            }
                          }}
                        />
                      ))
                    : null}
                </View>
              ))}
            </View>
          ))}
        </ScrollView>
      ) : null}
    </ScrollView>
  );
}

function Work({
  account,
  busy,
  sections,
  error,
  refreshing,
  onRefresh,
  onSettings,
  onCreate,
  onSignOut,
  onOpenIssue,
  onHome,
  onBoard,
  onBacklog,
  onSprints,
  onSchedules,
  onFind,
  onCalendar,
}) {
  return (
    <ScrollView
      contentContainerStyle={styles.workContent}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor="#0068B0"
        />
      }
      style={styles.work}
    >
      <View style={styles.toolbar}>
        <Text style={styles.signedIn}>Signed in as {account.displayName}</Text>
        <View style={styles.toolbarActions}>
          <TextButton label="Home" onPress={onHome} disabled={busy} />
          <TextButton label="Board" onPress={onBoard} disabled={busy} />
          <TextButton label="Backlog" onPress={onBacklog} disabled={busy} />
          <TextButton label="Sprints" onPress={onSprints} disabled={busy} />
          <TextButton label="Schedules" onPress={onSchedules} disabled={busy} />
          <TextButton label="Find" onPress={onFind} disabled={busy} />
          <TextButton label="Calendar" onPress={onCalendar} disabled={busy} />
          <TextButton label="Create" onPress={onCreate} disabled={busy} />
          <TextButton label="Settings" onPress={onSettings} disabled={busy} />
          <TextButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
      </View>
      {sections === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {sections && sections.length === 0 && !error ? (
        <Text style={styles.message}>{NO_PROJECTS}</Text>
      ) : null}
      {sections
        ? sections.map((section) => (
            <View key={section.projectId} style={styles.project}>
              <Text style={styles.projectName}>
                {section.projectKey} · {section.projectName}
              </Text>
              {!section.saved ? (
                <Text style={styles.message}>
                  This project has not been saved on this phone yet.
                </Text>
              ) : section.sprintName ? (
                <Text style={styles.sprintName}>{section.sprintName}</Text>
              ) : (
                <Text style={styles.message}>{NO_ACTIVE_SPRINT}</Text>
              )}
              {section.saved && section.sprintName && section.issues.length === 0 ? (
                <Text style={styles.message}>{NO_ISSUES}</Text>
              ) : null}
              {section.issues.map((issue) => (
                <Pressable
                  accessibilityLabel={`${issue.key || "New"} ${issue.title}`}
                  accessibilityRole="button"
                  key={issue.id}
                  onPress={() => onOpenIssue(issue.id)}
                  style={styles.issue}
                >
                  <Text style={styles.issueKey}>{issue.key || "New"}</Text>
                  <Text style={styles.issueTitle}>{issue.title}</Text>
                  <Text style={styles.issueStatus}>{issue.statusLabel}</Text>
                  {issue.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
                </Pressable>
              ))}
            </View>
          ))
        : null}
    </ScrollView>
  );
}

function IssueDetail({
  account,
  issueId,
  library,
  onBack,
  onUnauthorized,
  onRemember,
  onKeepPhone,
  onKeepServer,
  onRecreate,
  onDiscard,
  onUpdate,
  onDelete,
  onAddChild,
  onComment,
  onRemoveComment,
  onRepeat,
  onEditSeries,
}) {
  const [stack, setStack] = useState([issueId]);
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [childTitle, setChildTitle] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [relation, setRelation] = useState("blocks");
  const [linkKey, setLinkKey] = useState("");
  const currentId = stack[stack.length - 1];
  const saved = findIssue(library, currentId);
  const project = Object.values(library.projects || {}).find(
    (item) => item.issues && item.issues[currentId],
  ) || null;

  useEffect(() => {
    setStack([issueId]);
    setEditing(false);
  }, [issueId]);

  useEffect(() => {
    setEditing(false);
    setChildTitle("");
    setCommentBody("");
    setRelation("blocks");
    setLinkKey("");
  }, [currentId]);

  useEffect(() => {
    if (!saved || !saved.page) {
      return;
    }
    setPage((current) => {
      if (saved.pending || !current || !current.complete) {
        return saved.page;
      }
      const savedComments = saved.page.comments || [];
      const currentComments = current.comments || [];
      const sameComments = savedComments.length === currentComments.length
        && savedComments.every((comment, index) =>
          comment.id === currentComments[index].id && comment.pending === currentComments[index].pending);
      const extra = (saved.page.children || []).filter(
        (child) => !(current.children || []).some((item) => item.id === child.id),
      );
      if (sameComments && !extra.length) {
        return current;
      }
      return {
        ...current,
        comments: sameComments ? current.comments : savedComments,
        children: extra.length ? [...current.children, ...extra] : current.children,
      };
    });
  }, [library, currentId]);

  useEffect(() => {
    let active = true;
    setPage(saved && saved.page ? saved.page : null);
    setError("");
    if (Number(currentId) < 0) {
      return undefined;
    }
    loadIssueDetail(account.origin, account.token, currentId)
      .then(async (detail) => {
        if (!active) {
          return;
        }
        if (saved && (saved.pending || saved.conflict)) {
          return;
        }
        detail.page.complete = true;
        setPage(detail.page);
        await onRemember(detail.issue, detail.page);
      })
      .catch(async (err) => {
        if (!active) {
          return;
        }
        if (err.status === 401) {
          await onUnauthorized();
          return;
        }
        if (!(saved && saved.page)) {
          setError(err.message || "Could not connect.");
        }
      });
    return () => {
      active = false;
    };
  }, [account.origin, account.token, currentId]);

  function goBack() {
    if (editing) {
      setEditing(false);
      setError("");
      return;
    }
    if (stack.length <= 1) {
      onBack();
      return;
    }
    setStack((current) => current.slice(0, -1));
  }

  function askDelete() {
    const name = `${(page && page.key) || "New"} ${(saved && saved.raw && saved.raw.title) || ""}`.trim();
    Alert.alert(`Delete ${name}?`, "This cannot be undone.", [
      { text: "Keep it", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: () => {
          onDelete(currentId).then((failure) => {
            if (failure) {
              setError(failure);
            }
          });
        },
      },
    ]);
  }

  async function addChild() {
    const raw = saved && saved.raw;
    if (!raw) {
      return;
    }
    const type = raw.type === "epic" ? "story" : raw.type === "story" ? "subtask" : null;
    if (!type) {
      setError("A subtask cannot have children.");
      return;
    }
    if (Number(raw.id) < 0) {
      setError("This issue is not on the server yet.");
      return;
    }
    const prepared = prepareCreate({
      title: childTitle,
      projectId: raw.project_id,
      type,
      parent: { id: raw.id, type: raw.type, projectId: raw.project_id },
      sprintId: raw.sprint_id,
    });
    if (prepared.error) {
      setError(prepared.error);
      return;
    }
    const failure = await onAddChild(prepared.draft);
    if (failure) {
      setError(failure);
      return;
    }
    setChildTitle("");
    setError("");
  }

  async function reloadIssue() {
    const detail = await loadIssueDetail(account.origin, account.token, currentId);
    detail.page.complete = true;
    setPage(detail.page);
    await onRemember(detail.issue, detail.page);
  }

  async function addLink() {
    if (Number(currentId) < 0) {
      setError("This issue is not on the server yet.");
      return;
    }
    const parts = issueKeyParts(linkKey);
    if (!parts) {
      setError("Choose an issue to link.");
      return;
    }
    const ends = linkEnds(Number(currentId), 0, relation);
    if (!ends) {
      setError("That is not a valid dependency kind.");
      return;
    }
    try {
      let otherId = savedIssueId(library, linkKey);
      if (!otherId) {
        const projects = await read(account.origin, account.token, "/api/v1/projects");
        const project = (projects || []).find((item) => String(item.key).toUpperCase() === parts.key);
        const issues = project
          ? await read(account.origin, account.token, `/api/v1/projects/${project.id}/issues`)
          : [];
        const found = (issues || []).find((item) => Number(item.number) === parts.number);
        otherId = found ? found.id : null;
      }
      if (!otherId) {
        setError("Choose an issue to link.");
        return;
      }
      if (Number(otherId) === Number(currentId)) {
        setError("An issue cannot depend on itself.");
        return;
      }
      await send(account.origin, account.token, "POST", "/api/v1/dependencies", {
        ...linkEnds(Number(currentId), Number(otherId), relation),
      });
      await reloadIssue();
      setLinkKey("");
      setError("");
    } catch (err) {
      if (err.status === 401) {
        await onUnauthorized();
        return;
      }
      setError(err.message || "Could not connect.");
    }
  }

  async function removeLink(item) {
    if (!item.dependencyId) {
      return;
    }
    try {
      await send(account.origin, account.token, "DELETE", `/api/v1/dependencies/${item.dependencyId}`);
      await reloadIssue();
      setError("");
    } catch (err) {
      if (err.status === 401) {
        await onUnauthorized();
        return;
      }
      setError(err.message || "Could not connect.");
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.workContent} style={styles.work}>
      <TextButton label="Back" onPress={goBack} disabled={false} />
      {editing && saved && saved.raw ? (
        <EditIssue
          account={account}
          issue={saved.raw}
          library={library}
          page={page}
          project={project}
          onCancel={() => {
            setEditing(false);
            setError("");
          }}
          onSave={async (changes, options) => {
            const failure = await onUpdate(currentId, changes, options);
            if (failure) {
              return failure;
            }
            setEditing(false);
            return null;
          }}
        />
      ) : null}
      {saved && saved.conflict ? (
        <View style={styles.conflict}>
          <Text style={styles.pending}>{NOT_ON_SERVER}</Text>
          {saved.conflict.kind === "deleted" ? (
            <View>
              <Text style={styles.message}>The server no longer has this issue.</Text>
              <PrimaryButton label="File it again" onPress={() => onRecreate(currentId)} disabled={false} />
              <PrimaryButton label="Discard this copy" onPress={() => onDiscard(currentId)} disabled={false} />
            </View>
          ) : (
            <View>
              <Text style={styles.message}>
                This phone: {saved.raw.title}
              </Text>
              <Text style={styles.message}>
                Server: {saved.conflict.server.title}
              </Text>
              <PrimaryButton label="Keep this phone" onPress={() => onKeepPhone(currentId)} disabled={false} />
              <PrimaryButton
                label="Keep the server"
                onPress={() => onKeepServer(currentId, saved.conflict.server)}
                disabled={false}
              />
            </View>
          )}
        </View>
      ) : null}
      {saved && saved.error ? <Text style={styles.error}>{saved.error}</Text> : null}
      {!saved && page ? (
        <Text style={styles.message}>This issue is no longer in the saved sprint.</Text>
      ) : null}
      {page === null && !error ? <ActivityIndicator color="#0068B0" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!editing && page ? (
        <View>
          {saved && saved.pending && !(saved.conflict) ? (
            <Text style={styles.pending}>{NOT_ON_SERVER}</Text>
          ) : null}
          <Text style={styles.issueKey}>{page.key || "New"}</Text>
          <Text style={styles.detailTitle}>{page.title}</Text>
          {saved && saved.raw && !(saved.conflict) ? (
            <View style={styles.toolbarActions}>
              <TextButton label="Edit" onPress={() => setEditing(true)} disabled={false} />
              <TextButton label="Delete" onPress={askDelete} disabled={false} />
            </View>
          ) : null}
          <DetailLine label="Type" value={page.typeLabel} />
          <DetailLine label="Status" value={page.statusLabel} />
          <DetailLine label="Priority" value={page.priorityLabel} />
          <DetailLine label="Assignee" value={page.assignee} />
          <DetailLine label="Reporter" value={page.reporter} />
          <DetailLine label="Labels" value={page.labels} />
          <DetailLine label="Sprint" value={page.sprintName || "None"} />
          <DetailLine label="Start" value={page.start} />
          <DetailLine label="Due" value={page.due} />
          <DetailLine label="Estimate" value={page.estimate} />
          <DetailLine label="Remaining" value={page.remaining} />
          {page.rollup ? (
            <View>
              <DetailLine label="Rollup estimate" value={page.rollup.estimate} />
              <DetailLine label="Rollup remaining" value={page.rollup.remaining} />
              <DetailLine label="Progress" value={page.rollup.progress} />
              {page.rollup.cancelled ? (
                <DetailLine label="Cancelled" value={page.rollup.cancelled} />
              ) : null}
            </View>
          ) : null}
          <Text style={styles.sectionHeading}>Description</Text>
          <Markdown blocks={page.description} />
          <Text style={styles.sectionHeading}>Parent</Text>
          {page.parent ? (
            <LinkedRow item={page.parent} onPress={() => setStack((current) => [...current, page.parent.id])} />
          ) : (
            <Text style={styles.message}>None</Text>
          )}
          <Text style={styles.sectionHeading}>Children</Text>
          {page.children.length ? (
            page.children.map((child) => (
              <LinkedRow
                item={child}
                key={child.id}
                onPress={() => setStack((current) => [...current, child.id])}
              />
            ))
          ) : (
            <Text style={styles.message}>No children.</Text>
          )}
          {saved && saved.raw && saved.raw.type !== "subtask" && !(saved.conflict) ? (
            <View>
              <Field
                label={saved.raw.type === "epic" ? "Story title" : "Subtask title"}
                value={childTitle}
                onChange={setChildTitle}
              />
              <PrimaryButton
                label={saved.raw.type === "epic" ? "Add story" : "Add subtask"}
                onPress={addChild}
                disabled={false}
              />
            </View>
          ) : null}
          {page.formerSeries ? (
            <Text style={styles.message}>Was part of {page.formerSeries}.</Text>
          ) : null}
          {page.complete && (page.seriesId || (saved && saved.raw && saved.raw.series_id)) ? (
            <PrimaryButton
              label="Edit series"
              onPress={() => onEditSeries(page.seriesId || saved.raw.series_id, page)}
              disabled={false}
            />
          ) : null}
          {page.complete && !(page.seriesId || (saved && saved.raw && saved.raw.series_id)) && Number(currentId) > 0 ? (
            <PrimaryButton label="Make this repeating" onPress={() => onRepeat(page)} disabled={false} />
          ) : null}
          <LinkGroup
            title="Blocks"
            items={page.blocks}
            onOpen={(id) => setStack((current) => [...current, id])}
            onRemove={page.complete ? removeLink : null}
          />
          <LinkGroup
            title="Blocked by"
            items={page.blockedBy}
            onOpen={(id) => setStack((current) => [...current, id])}
            onRemove={page.complete ? removeLink : null}
          />
          <LinkGroup
            title="Relates to"
            items={page.relatesTo}
            onOpen={(id) => setStack((current) => [...current, id])}
            onRemove={page.complete ? removeLink : null}
          />
          {Number(currentId) < 0 ? (
            <Text style={styles.message}>This issue is not on the server yet.</Text>
          ) : page.complete ? (
            <View>
              <Text style={styles.sectionHeading}>Link an issue</Text>
              <Choice selected={relation === "blocks"} title="Blocks" onPress={() => setRelation("blocks")} />
              <Choice selected={relation === "blocked_by"} title="Blocked by" onPress={() => setRelation("blocked_by")} />
              <Choice selected={relation === "relates_to"} title="Relates to" onPress={() => setRelation("relates_to")} />
              <Field label="Issue" value={linkKey} onChange={setLinkKey} placeholder="KEEL-12" />
              <PrimaryButton label="Add link" onPress={addLink} disabled={false} />
            </View>
          ) : (
            <Text style={styles.message}>A link needs a connection.</Text>
          )}
          <Text style={styles.sectionHeading}>History</Text>
          {page.complete ? (
            page.historyAvailable ? (
              page.history.length ? (
                page.history.map((line, index) => (
                  <Text key={`${index}-${line}`} style={styles.historyLine}>
                    {line}
                  </Text>
                ))
              ) : (
                <Text style={styles.message}>No history yet.</Text>
              )
            ) : (
              <Text style={styles.message}>History is not on this server yet.</Text>
            )
          ) : (
            <Text style={styles.message}>
              History and links load the next time this phone reaches the server.
            </Text>
          )}
          <DetailLine label="Created" value={page.created} />
          <DetailLine label="Updated" value={page.updated} />
          <Text style={styles.sectionHeading}>Comments</Text>
          {(page.comments || []).length ? (
            (page.comments || []).map((comment) => (
              <View key={comment.id} style={styles.issue}>
                <Text style={styles.issueKey}>{comment.author} · {comment.created}</Text>
                <Markdown blocks={comment.blocks || []} />
                {comment.pending ? <Text style={styles.pending}>{NOT_ON_SERVER}</Text> : null}
                {saved && !(saved.conflict) ? (
                  <TextButton
                    label="Remove"
                    onPress={() => {
                      onRemoveComment(currentId, comment.id).then((failure) => {
                        if (failure) {
                          setError(failure);
                        }
                      });
                    }}
                    disabled={false}
                  />
                ) : null}
              </View>
            ))
          ) : page.complete ? (
            <Text style={styles.message}>No comments yet.</Text>
          ) : (
            <Text style={styles.message}>
              Comments load the next time this phone reaches the server.
            </Text>
          )}
          {saved && !(saved.conflict) ? (
            <View>
              <Field label="Comment" value={commentBody} onChange={setCommentBody} multiline />
              <PrimaryButton
                label="Add comment"
                onPress={async () => {
                  const failure = await onComment(currentId, commentBody);
                  if (failure) {
                    setError(failure);
                    return;
                  }
                  setCommentBody("");
                  setError("");
                }}
                disabled={false}
              />
            </View>
          ) : null}
        </View>
      ) : null}
    </ScrollView>
  );
}

function DetailLine({ label, value }) {
  return (
    <Text style={styles.detailLine}>
      <Text style={styles.detailLabel}>{label}: </Text>
      {value}
    </Text>
  );
}

function LinkedRow({ item, onPress }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.issue}>
      <Text style={styles.issueKey}>
        {item.key}
        {item.projectKey ? ` · ${item.projectKey}` : ""}
        {item.statusLabel ? ` · ${item.statusLabel}` : ""}
      </Text>
      <Text style={styles.issueTitle}>{item.title}</Text>
    </Pressable>
  );
}

function LinkGroup({ title, items, onOpen, onRemove }) {
  return (
    <View>
      <Text style={styles.sectionHeading}>{title}</Text>
      {items.length ? (
        items.map((item) => (
          <View key={item.dependencyId || item.id}>
            <LinkedRow item={item} onPress={() => onOpen(item.id)} />
            {onRemove && item.dependencyId ? (
              <TextButton label="Remove" onPress={() => onRemove(item)} disabled={false} />
            ) : null}
          </View>
        ))
      ) : (
        <Text style={styles.message}>None</Text>
      )}
    </View>
  );
}

function Markdown({ blocks }) {
  if (!blocks.length) {
    return <Text style={styles.message}>No description.</Text>;
  }
  return blocks.map((block, index) => {
    if (block.type === "code") {
      return (
        <Text key={index} style={styles.codeBlock}>
          {block.text}
        </Text>
      );
    }
    if (block.type === "list") {
      return (
        <View key={index}>
          {block.items.map((item, itemIndex) => (
            <Text key={itemIndex} style={styles.body}>
              {"• "}
              <Runs runs={item} />
            </Text>
          ))}
        </View>
      );
    }
    return (
      <Text key={index} style={block.type === "heading" ? styles.markdownHeading : styles.body}>
        <Runs runs={block.inlines} />
      </Text>
    );
  });
}

function Runs({ runs }) {
  return runs.map((run, index) => (
    <Text
      key={index}
      style={[
        run.bold ? styles.bold : null,
        run.italic ? styles.italic : null,
        run.code ? styles.inlineCode : null,
      ]}
    >
      {run.text}
    </Text>
  ));
}

function TextButton({ label, onPress, disabled }) {
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}>
      <Text style={styles.textButton}>{label}</Text>
    </Pressable>
  );
}

function SignedOut({
  address,
  username,
  password,
  busy,
  message,
  tone,
  onAddressChange,
  onUsername,
  onPassword,
  onCheck,
  onSignIn,
}) {
  return (
    <View>
      <Field
        label="Server address"
        value={address}
        onChange={onAddressChange}
        placeholder="http://192.168.1.122:8000"
        keyboardType="url"
        secure={false}
        disabled={busy}
      />
      <PrimaryButton label="Check" onPress={onCheck} disabled={busy} />
      <Field
        label="Username"
        value={username}
        onChange={onUsername}
        placeholder=""
        keyboardType="default"
        secure={false}
        disabled={busy}
      />
      <PasswordField value={password} onChange={onPassword} disabled={busy} />
      <PrimaryButton label="Sign in" onPress={onSignIn} disabled={busy} />
      {message ? (
        <Text style={[styles.message, tone === "ok" ? styles.ok : null, tone === "error" ? styles.error : null]}>
          {message}
        </Text>
      ) : null}
    </View>
  );
}

function PasswordField({ value, onChange, disabled }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <View>
      <Text style={styles.label}>Password</Text>
      <View style={styles.passwordRow}>
        <TextInput
          accessibilityLabel="Password"
          autoCapitalize="none"
          autoCorrect={false}
          editable={!disabled}
          onChangeText={(next) =>
            onChange(revealed ? next : applyPasswordEdit(value, next))
          }
          placeholderTextColor="#8AA0B2"
          secureTextEntry={false}
          style={[styles.input, styles.passwordInput]}
          value={revealed ? value : maskPassword(value)}
        />
        <Pressable
          accessibilityLabel={revealed ? "Hide password" : "Show password"}
          accessibilityRole="button"
          onPress={() => setRevealed((current) => !current)}
          style={styles.reveal}
        >
          <Text style={styles.revealText}>{revealed ? "Hide" : "Show"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Field({ label, value, onChange, placeholder, keyboardType, secure, disabled, multiline }) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        autoCapitalize={multiline ? "sentences" : "none"}
        autoCorrect={false}
        editable={!disabled}
        keyboardType={keyboardType}
        multiline={Boolean(multiline)}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#8AA0B2"
        secureTextEntry={secure}
        style={[styles.input, multiline ? styles.multiline : null]}
        value={value}
      />
    </View>
  );
}

function PrimaryButton({ label, onPress, disabled }) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.button, pressed && !disabled ? styles.buttonPressed : null]}
    >
      {disabled ? (
        <ActivityIndicator color="#FFFFFF" />
      ) : (
        <Text style={styles.buttonText}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 24,
    paddingTop: 72,
  },
  work: {
    flex: 1,
  },
  workContent: {
    paddingBottom: 32,
  },
  toolbar: {
    marginBottom: 8,
  },
  toolbarActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 16,
    marginTop: 8,
  },
  signedIn: {
    color: "#0062AB",
    fontSize: 16,
  },
  textButton: {
    color: "#0068B0",
    fontSize: 16,
    fontWeight: "700",
  },
  project: {
    marginTop: 20,
  },
  projectName: {
    color: "#0068B0",
    fontSize: 18,
    fontWeight: "700",
  },
  sprintName: {
    color: "#0062AB",
    fontSize: 15,
    marginTop: 4,
  },
  boardRow: {
    marginTop: 12,
  },
  boardColumn: {
    marginRight: 12,
    width: 260,
  },
  issue: {
    borderColor: "#0068B0",
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  issueKey: {
    color: "#0068B0",
    fontSize: 14,
    fontWeight: "700",
  },
  issueTitle: {
    color: "#0062AB",
    fontSize: 16,
    marginTop: 2,
  },
  issueStatus: {
    color: "#0F7A73",
    fontSize: 14,
    marginTop: 4,
  },
  calendarWeek: {
    flexDirection: "row",
    alignItems: "stretch",
  },
  calendarWeekday: {
    color: "#0062AB",
    flex: 1,
    fontSize: 12,
    fontWeight: "700",
    textAlign: "center",
  },
  calendarDay: {
    borderColor: "#D6E6F2",
    borderWidth: 1,
    flex: 1,
    minHeight: 72,
    padding: 2,
  },
  calendarMuted: {
    opacity: 0.45,
  },
  calendarToday: {
    backgroundColor: "#E8F3FB",
  },
  calendarDate: {
    color: "#0062AB",
    fontSize: 12,
    fontWeight: "700",
  },
  calendarChip: {
    fontSize: 10,
    fontWeight: "700",
  },
  calendarStatus: {
    color: "#0F7A73",
    fontSize: 9,
  },
  pending: {
    color: "#9A3412",
    fontSize: 14,
    fontWeight: "700",
    marginTop: 4,
  },
  projectSwitch: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
  },
  conflict: {
    borderColor: "#9A3412",
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 12,
  },
  detailTitle: {
    color: "#0062AB",
    fontSize: 22,
    fontWeight: "700",
    marginBottom: 8,
    marginTop: 4,
  },
  detailLine: {
    color: "#0062AB",
    fontSize: 16,
    marginTop: 6,
  },
  detailLabel: {
    fontWeight: "700",
  },
  sectionHeading: {
    color: "#0068B0",
    fontSize: 18,
    fontWeight: "700",
    marginTop: 20,
  },
  body: {
    color: "#0062AB",
    fontSize: 16,
    marginTop: 8,
  },
  markdownHeading: {
    color: "#0068B0",
    fontSize: 18,
    fontWeight: "700",
    marginTop: 12,
  },
  bold: {
    fontWeight: "700",
  },
  italic: {
    fontStyle: "italic",
  },
  inlineCode: {
    fontFamily: "monospace",
  },
  codeBlock: {
    backgroundColor: "#F3F7FB",
    color: "#0062AB",
    fontFamily: "monospace",
    fontSize: 14,
    marginTop: 8,
    padding: 12,
  },
  historyLine: {
    color: "#0062AB",
    fontSize: 15,
    marginTop: 8,
  },
  title: {
    color: "#0068B0",
    fontSize: 40,
    fontWeight: "700",
    marginBottom: 32,
  },
  label: {
    color: "#0062AB",
    fontSize: 16,
    marginBottom: 8,
    marginTop: 16,
  },
  input: {
    borderColor: "#0068B0",
    borderRadius: 8,
    borderWidth: 1,
    color: "#0062AB",
    fontSize: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  multiline: {
    minHeight: 96,
    textAlignVertical: "top",
  },
  passwordRow: {
    alignItems: "center",
    flexDirection: "row",
  },
  passwordInput: {
    flex: 1,
  },
  reveal: {
    marginLeft: 12,
    paddingVertical: 10,
  },
  revealText: {
    color: "#0068B0",
    fontSize: 16,
    fontWeight: "700",
  },
  button: {
    alignItems: "center",
    backgroundColor: "#0068B0",
    borderRadius: 8,
    marginTop: 16,
    minHeight: 48,
    justifyContent: "center",
  },
  buttonPressed: {
    backgroundColor: "#0062AB",
  },
  buttonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
  message: {
    color: "#0062AB",
    fontSize: 16,
    marginTop: 20,
  },
  ok: {
    color: "#0F7A73",
  },
  error: {
    color: "#9A3412",
  },
  choice: {
    paddingVertical: 8,
  },
  choiceText: {
    color: "#0062AB",
    fontSize: 16,
  },
});
