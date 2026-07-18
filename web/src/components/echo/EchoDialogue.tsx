import { memo } from "react";
import type { EchoScene, EchoTurn } from "../../lib/echoCourse";

type EchoDialogueProps = {
  scene: EchoScene;
  activeTurn: EchoTurn;
  completedTurnIds: Set<string>;
};

export const EchoDialogue = memo(function EchoDialogue({ scene, activeTurn, completedTurnIds }: EchoDialogueProps) {
  return (
    <ol className="echo-course__dialogue" aria-label={`${scene.title} dialogue`}>
      {scene.turns.map((turn) => {
        const active = turn.id === activeTurn.id;
        const completed = completedTurnIds.has(turn.id);
        return (
          <li
            key={turn.id}
            className={`echo-course__bubble echo-course__bubble--${turn.role} ${active ? "is-active" : ""} ${completed ? "is-complete" : ""}`}
            aria-current={active ? "step" : undefined}
          >
            <span className="echo-course__role">{turn.role === "minh" ? "Minh" : "You"}</span>
            <p lang="vi">{turn.text}</p>
            {active ? <small>{turn.gloss_en}</small> : null}
          </li>
        );
      })}
    </ol>
  );
});
