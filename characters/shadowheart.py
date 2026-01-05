# Define Shadowheart's D&D attributes and personality profile

SHADOWHEART_ATTRIBUTES = {
    # Basic Information
    "name": "Shadowheart",
    "race": "Half-Elf",
    "class": "Cleric",
    "subclass": "Trickery Domain",
    "deity": "Shar",
    "level": 1,
    
    # D&D 5e Ability Scores (Standard Array: 15, 14, 13, 12, 10, 8)
    "ability_scores": {
        "STR": 13,  # Strength
        "DEX": 14,  # Dexterity
        "CON": 14,  # Constitution
        "INT": 10,  # Intelligence
        "WIS": 15,  # Wisdom (Primary for Cleric)
        "CHA": 12,  # Charisma
    },
    
    # Ability Score Modifiers
    "ability_modifiers": {
        "STR": 1,
        "DEX": 2,
        "CON": 2,
        "INT": 0,
        "WIS": 2,
        "CHA": 1,
    },
    
    # Skills (Proficiency in Cleric skills)
    "skills": {
        "Insight": True,  # WIS + Proficiency
        "Religion": True,  # INT + Proficiency
        "Deception": True,  # CHA + Proficiency (from Trickery Domain)
        "Stealth": True,  # DEX + Proficiency (from Trickery Domain)
    },
    
    # Personality Traits
    "personality": {
        "traits": [
            "Mysterious and secretive about her past",
            "Devoted to Shar, the goddess of darkness and loss",
            "Skeptical of others but can form deep bonds",
            "Struggles with memory loss and hidden truths",
            "Practical and pragmatic in her approach",
        ],
        "ideals": "Faith in Shar and the necessity of loss and darkness",
        "bonds": "Her mission and the artifact she carries",
        "flaws": "Secretive nature and difficulty trusting others",
    },
    
    # Background
    "background": {
        "type": "Acolyte",
        "description": "A devoted follower of Shar, Shadowheart has dedicated her life to the goddess of darkness. She carries a mysterious artifact and has gaps in her memory that she struggles to understand.",
    },
    
    # Combat Stats
    "combat": {
        "armor_class": 16,  # Scale Mail (14) + DEX modifier (2)
        "hit_points": 10,  # 8 (Cleric base) + CON modifier (2)
        "hit_dice": "1d8",
        "speed": 30,  # feet per turn
        "proficiency_bonus": 2,
    },
    
    # Spells (Level 1 Cleric)
    "spells": {
        "cantrips": ["Guidance", "Sacred Flame", "Thaumaturgy"],
        "level_1": [
            "Bane",
            "Charm Person",
            "Cure Wounds",
            "Disguise Self",
            "Inflict Wounds",
            "Shield of Faith",
        ],
    },
    
    # Equipment
    "equipment": [
        "Mace",
        "Scale Mail",
        "Shield",
        "Holy Symbol of Shar",
        "Mysterious Artifact",
    ],
    
    # Dialogue Style
    "dialogue_style": {
        "tone": "Mysterious, guarded, but occasionally warm",
        "speech_patterns": [
            "Speaks in measured, thoughtful sentences",
            "Uses religious references to Shar",
            "Often questions others' motives",
            "Can be cryptic about her past",
        ],
        "common_phrases": [
            "Shar's will be done",
            "There's more to me than meets the eye",
            "Trust is earned, not given",
        ],
    },
}
