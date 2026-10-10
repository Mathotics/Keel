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
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { login, renameLabel, revokeToken } from "./src/api";
import { healthUrl, isConnected, parseOrigin } from "./src/origin";
import { ALWAYS, ON_LAUNCH, ON_RESUME, shouldUnlock } from "./src/lock";
import { applyPasswordEdit, maskPassword } from "./src/password";

const ADDRESS_KEY = "keel.serverAddress";
const LOCK_KEY = "keel.lockSetting";
const TOKEN_KEY = "keel.token";
const TOKEN_ID_KEY = "keel.tokenId";
const NAME_KEY = "keel.displayName";
const LABEL_KEY = "keel.label";
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
    const [savedAddress, savedLock, token, tokenId, displayName, label, level] =
      await Promise.all([
        AsyncStorage.getItem(ADDRESS_KEY),
        AsyncStorage.getItem(LOCK_KEY),
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(TOKEN_ID_KEY),
        SecureStore.getItemAsync(NAME_KEY),
        SecureStore.getItemAsync(LABEL_KEY),
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
    Alert.alert("Sign out", "Sign out of Keel on this phone?", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: signOut },
    ]);
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
    setAccount(null);
    setPassword("");
    setMessage("");
    setTone("idle");
    setPhase("signedOut");
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
        <View>
          <Text style={styles.label}>Signed in as {account.displayName}</Text>
          <Text style={styles.message}>This phone: {account.label}</Text>
          {message ? <Text style={styles.error}>{message}</Text> : null}
          <PrimaryButton label="Settings" onPress={openSettings} disabled={busy} />
          <PrimaryButton label="Sign out" onPress={onSignOut} disabled={busy} />
        </View>
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

function Field({ label, value, onChange, placeholder, keyboardType, secure, disabled }) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        autoCapitalize="none"
        autoCorrect={false}
        editable={!disabled}
        keyboardType={keyboardType}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#8AA0B2"
        secureTextEntry={secure}
        style={styles.input}
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
