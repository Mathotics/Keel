import { useEffect, useState } from "react";
import { StatusBar } from "expo-status-bar";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const { healthUrl, isConnected, parseOrigin } = require("./src/origin");

const STORAGE_KEY = "keel.serverAddress";
const CONNECTED = "Connected";
const FAILED = "Could not connect.";
const TIMEOUT_MS = 5000;

export default function App() {
  const [address, setAddress] = useState("");
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const [tone, setTone] = useState("idle");

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (!active) {
        return;
      }
      if (saved) {
        setAddress(saved);
      } else {
        setMessage("Enter the server address.");
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  async function persist(value) {
    if (value) {
      await AsyncStorage.setItem(STORAGE_KEY, value);
    } else {
      await AsyncStorage.removeItem(STORAGE_KEY);
    }
  }

  function onChange(value) {
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
        await persist("");
      }
      return;
    }

    await persist(parsed.origin);
    setAddress(parsed.origin);
    setChecking(true);
    setTone("idle");
    setMessage("");

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
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
      setChecking(false);
    }
  }

  return (
    <View style={styles.screen}>
      <StatusBar style="dark" />
      <Text style={styles.title}>Keel</Text>
      <Text style={styles.label}>Server address</Text>
      <TextInput
        accessibilityLabel="Server address"
        autoCapitalize="none"
        autoCorrect={false}
        editable={ready && !checking}
        keyboardType="url"
        onChangeText={onChange}
        placeholder="http://192.168.1.122:8000"
        placeholderTextColor="#8AA0B2"
        style={styles.input}
        value={address}
      />
      <Pressable
        accessibilityRole="button"
        disabled={!ready || checking}
        onPress={onCheck}
        style={({ pressed }) => [
          styles.button,
          pressed && ready && !checking ? styles.buttonPressed : null,
        ]}
      >
        {checking ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.buttonText}>Check</Text>
        )}
      </Pressable>
      {message ? (
        <Text
          style={[
            styles.message,
            tone === "ok" ? styles.ok : null,
            tone === "error" ? styles.error : null,
          ]}
        >
          {message}
        </Text>
      ) : null}
    </View>
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
});
