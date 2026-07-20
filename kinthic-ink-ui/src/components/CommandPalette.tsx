import React, { memo } from 'react';

import { Box, Text } from 'ink';

import { colors } from '../theme.js';



export interface CommandSpec {

  cmd: string;

  args: string;

  desc: string;

}



interface CommandPaletteProps {

  query: string;

  commands: CommandSpec[];

  selectedIndex: number;

}



function renderMatch(cmd: string, query: string): React.ReactNode {

  const q = query.toLowerCase();

  const idx = cmd.toLowerCase().indexOf(q);

  if (!q || idx < 0) return <Text color={colors.gold} bold>{cmd}</Text>;

  return (

    <>

      <Text color={colors.gold} bold>{cmd.slice(0, idx)}</Text>

      <Text color={colors.white} inverse>{cmd.slice(idx, idx + q.length)}</Text>

      <Text color={colors.gold} bold>{cmd.slice(idx + q.length)}</Text>

    </>

  );

}



const CommandPalette = memo(({ query, commands, selectedIndex }: CommandPaletteProps) => {

  if (commands.length === 0) return null;



  const visible = commands.slice(0, 6);



  return (

    <Box flexDirection="column" marginTop={1} paddingLeft={2}>

      {visible.map((cmd, idx) => {

        const active = idx === selectedIndex;

        return (

          <Box key={`${cmd.cmd}-${cmd.args}`}>

            <Box width={2}>

              <Text color={active ? colors.gold : colors.dimWhite}>{active ? '›' : ' '}</Text>

            </Box>

            <Box width={28}>{renderMatch(cmd.cmd, query)}</Box>

            <Text color={active ? colors.white : colors.dimWhite}>{cmd.args}</Text>

            <Text color={active ? colors.white : colors.dimWhite} dimColor={!active}>

              {'  '}{cmd.desc}

            </Text>

          </Box>

        );

      })}

      <Box marginTop={1}>

        <Text color={colors.dimWhite}>Tab accept · ↑↓ · Esc close</Text>

      </Box>

    </Box>

  );

});



export default CommandPalette;

