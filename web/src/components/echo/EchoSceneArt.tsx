import { memo, useState } from "react";
import type { EchoScene } from "../../lib/echoCourse";

export const EchoSceneArt = memo(function EchoSceneArt({ scene }: { scene: EchoScene }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className={`echo-course__scene-art ${failed ? "echo-course__scene-art--fallback" : ""}`}>
      {!failed ? <img src={scene.art_url} alt={scene.art_alt} onError={() => setFailed(true)} /> : null}
      <div className="echo-course__scene-scrim" />
      <div className="echo-course__scene-caption">
        <span>Scene {scene.number} of 4</span>
        <strong>{scene.title}</strong>
        <small>{scene.location}</small>
      </div>
    </div>
  );
});
