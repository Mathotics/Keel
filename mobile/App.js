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

import { loadCatalog, loadIssueDetail, loadProfile, loadSnapshots, login, read, renameLabel, revokeToken, send } from "./src/api";
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
  queueCreate,
  queueDelete,
  queueRecreate,
  queueUpdate,
  rememberDetail,
  storeKey,
  workView,
} from "./src/offline";
import { pullLibrary } from "./src/sync";
import { inputWhen, prepareCreate, prepareUpdate } from "./src/create";
import { formatMinutes } from "./src/issue";

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
    setPhase(next.signedIn ? "signedIn" : "signedOut");
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
      setPhase(result.success ? "signedIn" : "locked");
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
      setPhase("signedIn");
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
        await refreshLibrary(account, store);
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
      {phase === "signedIn" && account ? (
        <Work
          account={account}
          busy={busy}
          error={workError}
          onOpenIssue={(id) => {
            setIssueId(id);
            setPhase("issue");
          }}
          onCreate={() => {
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
      {phase === "create" && account ? (
        <CreateIssue
          account={account}
          busy={busy}
          library={library}
          onCancel={() => setPhase("signedIn")}
          onFile={async (draft) => {
            const filed = queueCreate(library, draft);
            if (filed.error) {
              return filed.error;
            }
            await persistLibrary(account.userId, filed.store);
            setPhase("signedIn");
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
          onBack={() => setPhase("signedIn")}
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
            setPhase("signedIn");
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
              setPhase("signedIn");
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
}) {
  const [stack, setStack] = useState([issueId]);
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [childTitle, setChildTitle] = useState("");
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
  }, [currentId]);

  useEffect(() => {
    if (!saved || !saved.page) {
      return;
    }
    setPage((current) => {
      if (saved.pending || !current || !current.complete) {
        return saved.page;
      }
      const extra = (saved.page.children || []).filter(
        (child) => !(current.children || []).some((item) => item.id === child.id),
      );
      if (!extra.length) {
        return current;
      }
      return { ...current, children: [...current.children, ...extra] };
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
          <LinkGroup
            title="Blocks"
            items={page.blocks}
            onOpen={(id) => setStack((current) => [...current, id])}
          />
          <LinkGroup
            title="Blocked by"
            items={page.blockedBy}
            onOpen={(id) => setStack((current) => [...current, id])}
          />
          <LinkGroup
            title="Relates to"
            items={page.relatesTo}
            onOpen={(id) => setStack((current) => [...current, id])}
          />
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

function LinkGroup({ title, items, onOpen }) {
  return (
    <View>
      <Text style={styles.sectionHeading}>{title}</Text>
      {items.length ? (
        items.map((item) => (
          <LinkedRow item={item} key={item.id} onPress={() => onOpen(item.id)} />
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
