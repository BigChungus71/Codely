"use client";

import { useTemplateCopy } from "@/components/foundations/template-copy/template-copy";

import { useState } from "react";
import { Select, SelectItem } from "@/components/base/select/select";
import { Switch } from "@/components/base/switch/switch";
import {
  SettingsCard,
  SettingsRow,
  SettingsSectionLabel,
} from "./settings-rows";

/**
 * Codely — General settings panel.
 *
 * Sections, 24px apart:
 *   developer     "Developer Mode" toggle — enables raw scan output & verbose logs.
 *   pull requests two select rows (Review provider / PR destination).
 *   notifications four toggle rows, only "Critical requests" on by default.
 */

/** Compact white select trigger (h 32, radius/lg) per the Figma rows. */
const SELECT_TRIGGER = "h-8 w-auto gap-1 rounded-lg px-2 py-1.5";

export function SettingsGeneral({ planArtSrc: _ }: { planArtSrc?: string }) {
  const localize = useTemplateCopy();
  const [toggles, setToggles] = useState({
    developerMode: false,
    critical: true,
    system: false,
    sound: false,
    dispatch: false,
  });

  const setToggle = (key: keyof typeof toggles) => (value: boolean) =>
    setToggles((t) => ({ ...t, [key]: value }));

  return localize((
    <div className="flex w-full flex-col gap-6">
      {/* Developer Mode */}
      <SettingsCard>
        <SettingsRow
          label="Developer Mode"
          description="Enable advanced tooling, raw scan output, and verbose logs."
        >
          <Switch
            aria-label="Developer Mode"
            isSelected={toggles.developerMode}
            onChange={setToggle("developerMode")}
          />
        </SettingsRow>
      </SettingsCard>

      {/* Pull Requests */}
      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Pull Requests</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Review provider"
            description="Select Github or other providers for reviews"
          >
            <Select
              aria-label="Review provider"
              defaultSelectedKey="github"
              triggerClassName={SELECT_TRIGGER}
            >
              <SelectItem id="github">GitHub</SelectItem>
              <SelectItem id="gitlab">GitLab</SelectItem>
              <SelectItem id="bitbucket">Bitbucket</SelectItem>
            </Select>
          </SettingsRow>
          <SettingsRow
            label="PR destination"
            description="Open pull request links inside your app"
          >
            <Select
              aria-label="PR destination"
              defaultSelectedKey="inside"
              triggerClassName={SELECT_TRIGGER}
            >
              <SelectItem id="inside">Inside Codely</SelectItem>
              <SelectItem id="browser">In the browser</SelectItem>
            </Select>
          </SettingsRow>
        </SettingsCard>
      </div>

      {/* Notifications */}
      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Notifications</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Critical requests"
            description="Get notified when the mode needs to make a critical decision"
          >
            <Switch
              aria-label="Critical requests"
              isSelected={toggles.critical}
              onChange={setToggle("critical")}
            />
          </SettingsRow>
          <SettingsRow
            label="System notifications"
            description="Show fundamental notifications when an agent completes a task"
          >
            <Switch
              aria-label="System notifications"
              isSelected={toggles.system}
              onChange={setToggle("system")}
            />
          </SettingsRow>
          <SettingsRow
            label="Completion sound"
            description="Sound effect a task is completed"
          >
            <Switch
              aria-label="Completion sound"
              isSelected={toggles.sound}
              onChange={setToggle("sound")}
            />
          </SettingsRow>
          <SettingsRow
            label="Dispatch alerts"
            description="Push notification on your phone when Codely messages you"
          >
            <Switch
              aria-label="Dispatch alerts"
              isSelected={toggles.dispatch}
              onChange={setToggle("dispatch")}
            />
          </SettingsRow>
        </SettingsCard>
      </div>
    </div>
  ));
}
